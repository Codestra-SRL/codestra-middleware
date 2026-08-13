"""Durable, typed BREERO CRM delivery from middleware to Odoo."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import SessionFactory

CLAIM = text("""
WITH claimable AS (
  SELECT id FROM breero_odoo_outbox
  WHERE status IN ('pending','retry_wait') AND COALESCE(next_attempt_at,now()) <= now()
  ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT :limit
)
UPDATE breero_odoo_outbox item SET status='leased',attempts=item.attempts+1,
 lease_token=:token,lease_expires_at=now()+make_interval(secs=>:lease),updated_at=now()
FROM claimable WHERE item.id=claimable.id
RETURNING item.id,item.receipt_public_id,item.attempts,item.lease_token
""")

LOAD = text("""SELECT r.event_id,r.event_type,r.aggregate_id,r.aggregate_version,
 r.payload,r.payload_hash,r.environment,r.route_key
FROM breero_event_receipt r WHERE r.public_id=:receipt""")

RECOVER = text("""UPDATE breero_odoo_outbox SET status='retry_wait',lease_token=NULL,
 lease_expires_at=NULL,next_attempt_at=now(),last_safe_error='STALE_LEASE_RECOVERED',updated_at=now()
WHERE status='leased' AND lease_expires_at < now()""")


class DeliveryError(RuntimeError):
    def __init__(self, code: str, *, terminal: bool = False):
        super().__init__(code)
        self.code, self.terminal = code, terminal


class Client(Protocol):
    async def deliver(self, envelope: dict[str, Any]) -> dict[str, Any]: ...
    async def aclose(self) -> None: ...


class OdooClient:
    def __init__(self) -> None:
        try:
            key = Path(settings.breero_odoo_api_key_file).read_text().strip()
        except OSError as exc:
            raise DeliveryError("ODOO_KEY_UNAVAILABLE", terminal=True) from exc
        if not all((settings.breero_odoo_url, settings.breero_odoo_database,
                    settings.breero_odoo_username, key)):
            raise DeliveryError("ODOO_CONFIGURATION_INCOMPLETE", terminal=True)
        self.key = key
        self.http = httpx.AsyncClient(
            timeout=20, verify=settings.breero_odoo_ca_file or True, follow_redirects=False
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    async def deliver(self, envelope: dict[str, Any]) -> dict[str, Any]:
        rpc = {"jsonrpc":"2.0","method":"call","id":str(uuid4()),"params":{
            "service":"object","method":"execute_kw","args":[settings.breero_odoo_database,
            settings.breero_odoo_username,self.key,"breero.sync.event","process_breero_event",[envelope],{}]}}
        try:
            response = await self.http.post(settings.breero_odoo_url.rstrip("/")+"/jsonrpc", json=rpc)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise DeliveryError("ODOO_UNAVAILABLE") from exc
        if response.status_code in {408,429,500,502,503,504}:
            raise DeliveryError(f"ODOO_HTTP_{response.status_code}")
        if response.status_code != 200:
            raise DeliveryError(f"ODOO_HTTP_{response.status_code}", terminal=True)
        try:
            document = response.json()
        except ValueError as exc:
            raise DeliveryError("ODOO_INVALID_RESPONSE", terminal=True) from exc
        if document.get("error"):
            name = str(document["error"].get("data",{}).get("name",""))
            terminal = any(x in name for x in ("AccessDenied","AccessError","ValidationError"))
            raise DeliveryError("ODOO_AUTH_OR_VALIDATION" if terminal else "ODOO_RPC_ERROR", terminal=terminal)
        ack = document.get("result")
        if not isinstance(ack,dict) or ack.get("event_id") != envelope["event_id"] or not ack.get("odoo_record_id"):
            raise DeliveryError("ODOO_ACK_BINDING_INVALID", terminal=True)
        return ack


async def recover_stale(session: AsyncSession) -> int:
    result = await session.execute(RECOVER)
    await session.commit()
    return int(result.rowcount or 0) if isinstance(result, CursorResult) else 0


async def _failure(session: AsyncSession, item: dict, error: DeliveryError) -> None:
    terminal = error.terminal or item["attempts"] >= settings.breero_odoo_max_attempts
    delay = min(300, 2 ** min(item["attempts"], 8))
    await session.execute(text("""UPDATE breero_odoo_outbox SET status=:status,
      next_attempt_at=CASE WHEN :terminal THEN NULL ELSE now()+make_interval(secs=>:delay) END,
      lease_token=NULL,lease_expires_at=NULL,last_safe_error=:error,updated_at=now()
      WHERE id=:id AND lease_token=:token"""), {"status":"dead_letter" if terminal else "retry_wait",
      "terminal":terminal,"delay":delay,"error":error.code,"id":item["id"],"token":item["lease_token"]})
    await session.execute(text("""UPDATE breero_event_receipt SET status=:status,updated_at=now()
      WHERE public_id=:receipt"""), {"status":"dead_letter" if terminal else "retry_wait","receipt":item["receipt_public_id"]})
    await session.execute(text("""INSERT INTO breero_integration_audit(receipt_public_id,action,outcome,safe_detail)
      VALUES (:receipt,'odoo.delivery.failed',:outcome,:detail)"""), {"receipt":item["receipt_public_id"],"outcome":"terminal" if terminal else "retry","detail":error.code})
    await session.commit()


async def cycle(client: Client | None = None) -> int:
    if not settings.breero_odoo_delivery_enabled:
        return 0
    token = uuid4()
    async with SessionFactory() as session:
        await recover_stale(session)
        items = (await session.execute(CLAIM,{"limit":settings.breero_odoo_batch_size,
            "token":token,"lease":settings.breero_odoo_lease_seconds})).mappings().all()
        await session.commit()
    owns = client is None
    transport = client or OdooClient()
    try:
        for item in items:
            async with SessionFactory() as session:
                row=(await session.execute(LOAD,{"receipt":item["receipt_public_id"]})).mappings().one()
                envelope={"event_id":str(row["event_id"]),"event_type":row["event_type"],"schema_version":1,
                    "aggregate_id":str(row["aggregate_id"]),"aggregate_version":row["aggregate_version"],
                    "occurred_at":datetime.now(UTC).isoformat(),"idempotency_key":item["receipt_public_id"],
                    "source":"breero","payload":row["payload"]}
                try:
                    ack=await transport.deliver(envelope)
                except DeliveryError as exc:
                    await _failure(session,dict(item),exc)
                    continue
                await session.execute(text("""UPDATE breero_odoo_outbox SET status='delivered',
                  lease_token=NULL,lease_expires_at=NULL,next_attempt_at=NULL,last_safe_error=NULL,
                  odoo_model=:model,odoo_record_id=:record,updated_at=now()
                  WHERE id=:id AND lease_token=:token"""),{"model":ack.get("odoo_model"),"record":ack["odoo_record_id"],"id":item["id"],"token":item["lease_token"]})
                await session.execute(text("UPDATE breero_event_receipt SET status='delivered',updated_at=now() WHERE public_id=:r"),{"r":item["receipt_public_id"]})
                await session.execute(text("INSERT INTO breero_integration_audit(receipt_public_id,action,outcome,safe_detail) VALUES (:r,'odoo.delivery','delivered',:d)"),{"r":item["receipt_public_id"],"d":str(ack.get("odoo_model",""))})
                await session.commit()
    finally:
        if owns:
            await transport.aclose()
    return len(items)


async def run_forever() -> None:
    while True:
        await cycle()
        await asyncio.sleep(1)
