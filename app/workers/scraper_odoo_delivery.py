"""Durable, staging-only delivery of validated scraper leads to Odoo."""

from __future__ import annotations

import asyncio
from typing import Mapping

import httpx
from sqlalchemy import text

from app.adapters.odoo.lead_automation import (
    OdooLeadApplyClient,
    TransportResponse,
)
from app.core.config import settings
from app.core.reliability import RetryPolicy
from app.db.session import SessionFactory
from app.workers.outbox import acknowledge, record_failure, recover_expired_leases


CLAIM = text("""
WITH claimable AS (
    SELECT id FROM outbox_event
    WHERE topic='sales.lead.odoo.apply'
      AND status IN ('pending', 'retry')
      AND (next_attempt_at IS NULL OR next_attempt_at <= now())
    ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT :limit
)
UPDATE outbox_event AS item SET status='processing', locked_at=now(),
    next_attempt_at=now() + make_interval(secs => :lease)
FROM claimable WHERE item.id=claimable.id
RETURNING item.id,item.payload,item.attempts
""")


def _transport(
    method: str,
    path: str,
    body: bytes,
    headers: Mapping[str, str],
    timeout: float,
) -> TransportResponse:
    url = settings.scraper_odoo_apply_url.rstrip("/") + path
    response = httpx.request(method, url, content=body, headers=headers, timeout=timeout)
    return TransportResponse(response.status_code, response.content)


async def deliver_once(*, limit: int = 8, lease_seconds: int = 60) -> int:
    if not settings.scraper_middleware_delivery_enabled:
        return 0
    client = OdooLeadApplyClient(
        secret=settings.lead_automation_hmac_secret.encode(),
        transport=_transport,
    )
    async with SessionFactory() as session:
        await recover_expired_leases(session)
        rows = (
            await session.execute(CLAIM, {"limit": limit, "lease": lease_seconds})
        ).mappings().all()
        await session.commit()
    for row in rows:
        try:
            await asyncio.to_thread(client.apply, row["payload"])
        except Exception as exc:
            async with SessionFactory() as session:
                await record_failure(
                    session,
                    row["id"],
                    int(row["attempts"]),
                    type(exc).__name__,
                    RetryPolicy(max_attempts=8, base_seconds=1, max_seconds=60),
                )
        else:
            async with SessionFactory() as session:
                await acknowledge(session, row["id"])
    return len(rows)


async def run_forever() -> None:
    while True:
        await deliver_once()
        await asyncio.sleep(1)
