"""Durable delivery of agent interaction results (AGENT-01) into Odoo.

The write to `interaction_result` already happened synchronously in the
request that answered the agent -- this worker's only job is to get that
already-durable fact into Odoo's `crm.lead`, retrying on failure and
dead-lettering (never silently dropping) after repeated failures. Delivery
failure here does not change what the agent was told: the write was already
real and durable before the HTTP response was sent.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.reliability import RetryPolicy
from app.db.session import SessionFactory
from app.workers.outbox import acknowledge, record_failure, recover_expired_leases

CLAIM = text("""
WITH claimable AS (
    SELECT id FROM outbox_event
    WHERE topic='interaction.result.recorded'
      AND status IN ('pending', 'retry')
      AND (next_attempt_at IS NULL OR next_attempt_at <= now())
    ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT :limit
)
UPDATE outbox_event AS item SET status='processing', locked_at=now(),
    next_attempt_at=now() + make_interval(secs => :lease)
FROM claimable WHERE item.id=claimable.id
RETURNING item.id, item.payload, item.attempts, item.correlation_id
""")

MARK_DELIVERED = text("""
UPDATE interaction_result
SET delivery_status='delivered', odoo_event_id=:odoo_event_id, updated_at=now()
WHERE id=:interaction_result_id
""")

MARK_FAILED = text("""
UPDATE interaction_result
SET delivery_status=:status, delivery_attempts=delivery_attempts+1,
    delivery_last_error=:error, updated_at=now()
WHERE id=:interaction_result_id
""")


class InteractionDeliveryError(RuntimeError):
    pass


def _sign(secret: str, ts: str, body: bytes) -> str:
    return hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()


async def _deliver_to_odoo(payload: dict[str, Any], correlation_id: str) -> str:
    if not settings.odoo_base_url:
        raise InteractionDeliveryError("odoo_base_url is not configured")
    if not settings.interaction_result_hmac_secret:
        raise InteractionDeliveryError("interaction_result_hmac_secret is not configured")
    event_type_map = {
        "notes": "interaction.notes.recorded",
        "disposition": "interaction.disposition.recorded",
        "callback": "interaction.callback.scheduled",
    }
    event_type = event_type_map.get(payload["result_type"])
    if not event_type:
        raise InteractionDeliveryError(f"unknown result_type {payload['result_type']!r}")
    body_dict = {"event_type": event_type, **payload}
    body = json.dumps(body_dict, sort_keys=True, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    event_id = payload["interaction_result_id"]
    signature = _sign(settings.interaction_result_hmac_secret, ts, body)
    url = settings.odoo_base_url.rstrip("/") + "/codestra/api/v1/events"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Codestra-Timestamp": ts,
                "X-Codestra-Signature": signature,
                "X-Codestra-Event-ID": event_id,
            },
        )
    if response.status_code not in (200, 202):
        raise InteractionDeliveryError(
            f"Odoo rejected interaction result delivery: {response.status_code}"
        )
    accepted = response.json()
    odoo_id = accepted.get("id")
    if odoo_id is None:
        raise InteractionDeliveryError("Odoo delivery acknowledgement missing id")
    return str(odoo_id)


async def deliver_once(*, limit: int = 16, lease_seconds: int = 60) -> int:
    async with SessionFactory() as session:
        await recover_expired_leases(session)
        rows = (
            await session.execute(CLAIM, {"limit": limit, "lease": lease_seconds})
        ).mappings().all()
        await session.commit()
    for row in rows:
        payload = row["payload"]
        interaction_result_id = payload["interaction_result_id"]
        try:
            odoo_event_id = await _deliver_to_odoo(payload, row["correlation_id"])
        except Exception as exc:
            async with SessionFactory() as session:
                status = await record_failure(
                    session,
                    row["id"],
                    int(row["attempts"]),
                    str(exc),
                    RetryPolicy(max_attempts=12, base_seconds=2, max_seconds=300),
                )
                await session.execute(
                    MARK_FAILED,
                    {
                        "interaction_result_id": UUID(interaction_result_id),
                        "status": "dead_letter" if status == "dead_letter" else "failed",
                        "error": str(exc)[:2000],
                    },
                )
                await session.commit()
        else:
            async with SessionFactory() as session:
                await acknowledge(session, row["id"])
                await session.execute(
                    MARK_DELIVERED,
                    {
                        "interaction_result_id": UUID(interaction_result_id),
                        "odoo_event_id": odoo_event_id,
                    },
                )
                await session.commit()
    return len(rows)


async def run_forever(*, poll_seconds: float = 2.0) -> None:
    while True:
        delivered = await deliver_once()
        await asyncio.sleep(poll_seconds if delivered == 0 else 0.1)
