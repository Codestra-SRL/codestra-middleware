import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import uuid4
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.db.models import (
    AuditEvent,
    EventInbox,
    IntegrationDelivery,
    IntegrationEvent,
    IdempotencyRecord,
    OutboxEvent,
    PolicyDecision,
    ReconciliationCheckpoint,
    TransferPolicyDecision,
)
from app.core.automation import canonical_hash
from app.core.reliability import authorize_transfer, redact, sanitize_for_storage

router = APIRouter(prefix="/api/v1", tags=["control-plane"])


class Envelope(BaseModel):
    model_config = ConfigDict(extra="allow")
    event_id: str | None = None
    campaign_id: str | None = None
    payload: dict[str, Any] = {}


class CanonicalOdooEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(pattern=r"^lead\.hot$")
    event_version: str = Field(pattern=r"^1\.0$")
    occurred_at: datetime
    received_at: datetime
    tenant_id: str = Field(min_length=1, max_length=128)
    environment: str = Field(pattern=r"^staging$")
    request_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=16, max_length=255)
    source: str = Field(pattern=r"^odoo$")
    campaign_id: str = Field(pattern=r"^TEST_SYN$")
    originating_odoo_outbox_id: str = Field(min_length=1, max_length=128)
    synthetic: bool
    references: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class Callback(BaseModel):
    phone: str = Field(min_length=7, max_length=32)
    lead_id: int
    scheduled_for: str
    note: str | None = None


class Transfer(BaseModel):
    lead_id: int
    target: str
    reason: str | None = None
    campaign_id: str = "TEST_SYN"
    do_not_call: bool = False


class Compliance(BaseModel):
    event_type: str
    lead_id: int | None = None
    payload: dict[str, Any] = {}


class Recommendation(BaseModel):
    recommendation: str
    reason: str | None = None


class Idem:
    @staticmethod
    async def check(db, key, scope, body):
        if not key:
            raise HTTPException(400, "Idempotency-Key is required")
        h = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        kh = hashlib.sha256(key.encode()).hexdigest()
        row = await db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == scope, IdempotencyRecord.key_hash == kh
            )
        )
        if row and row.request_hash != h:
            raise HTTPException(409, "idempotency key conflict")
        return row, h, kh


async def persist(
    db, action, subject, correlation, payload, allowed=True, reason="accepted"
):
    redacted = redact(payload)
    db.add(
        AuditEvent(
            action=action,
            subject=subject,
            correlation_id=correlation,
            decision="allow" if allowed else "deny",
            redacted_payload=redacted,
        )
    )
    db.add(
        PolicyDecision(
            policy=action,
            allowed=allowed,
            reason=reason,
            correlation_id=correlation,
            context=redacted,
        )
    )
    await db.flush()


@router.post("/events/odoo", status_code=202)
@router.post("/events/vicidial", status_code=202)
async def event(
    request: Request,
    body: CanonicalOdooEvent,
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
):
    if not body.synthetic:
        raise HTTPException(403, "only synthetic staging events are permitted")
    if x_correlation_id != body.correlation_id:
        raise HTTPException(409, "correlation header mismatch")
    if idempotency_key != body.idempotency_key:
        raise HTTPException(409, "idempotency header mismatch")
    corr = body.correlation_id
    raw = body.model_dump(mode="json")
    stored = sanitize_for_storage(raw)
    row, h, kh = await Idem.check(db, body.idempotency_key, "events:odoo:staging", raw)
    if row:
        return row.response
    prior = await db.scalar(
        select(IntegrationEvent).where(
            IntegrationEvent.original_event_id == body.event_id
        )
    )
    if prior:
        raise HTTPException(409, "event identity conflict")
    canonical = IntegrationEvent(
        idempotency_key=body.idempotency_key,
        event_type=body.event_type,
        schema_version=body.event_version,
        original_event_id=body.event_id,
        entity_key=str(body.references.get("odoo_record_id") or body.event_id),
        source_system="odoo",
        correlation_id=body.correlation_id,
        environment=body.environment,
        originating_odoo_outbox_id=body.originating_odoo_outbox_id,
        payload_json=stored,
        payload_hash=canonical_hash(stored),
        state="queued",
    )
    db.add(canonical)
    await db.flush()
    db.add(
        EventInbox(
            integration_event_id=canonical.id,
            event_id=body.event_id,
            source="odoo",
            event_type=body.event_type,
            payload=stored,
            correlation_id=corr,
        )
    )
    outbox = OutboxEvent(
        integration_event_id=canonical.id,
        topic="event.accepted", payload=stored, correlation_id=corr,
    )
    db.add(outbox)
    db.add_all(
        [
            IntegrationDelivery(
                event_id=canonical.id, target="n8n", status="pending"
            ),
            IntegrationDelivery(
                event_id=canonical.id, target="odoo", status="disabled"
            ),
        ]
    )
    await db.flush()
    await persist(db, "event.ingest", body.event_id, corr, stored)
    response = {
        "accepted": True,
        "event_id": body.event_id,
        "status": "queued",
        "correlation_id": corr,
        "middleware_outbox_id": str(outbox.id),
    }
    db.add(
        IdempotencyRecord(
            scope="events:odoo:staging",
            key_hash=kh,
            request_hash=h,
            response=response,
            status_code=202,
            event_id=canonical.id,
        )
    )
    await db.commit()
    return response


@router.get("/events/{event_id}")
async def event_status(event_id: str, db: AsyncSession = Depends(get_session)):
    row = await db.scalar(select(EventInbox).where(EventInbox.event_id == event_id))
    if not row:
        raise HTTPException(404, "event not found")
    return {
        "event_id": row.event_id,
        "status": row.status,
        "correlation_id": row.correlation_id,
    }


async def mutation(path, body, db, key, corr):
    raw = body.model_dump()
    row, h, kh = await Idem.check(db, key, path, raw)
    if row:
        return row.response
    ident = str(uuid4())
    await persist(db, path, ident, corr, raw)
    response = {"id": ident, "status": "accepted", "correlation_id": corr}
    db.add(
        IdempotencyRecord(
            scope=path, key_hash=kh, request_hash=h, response=response, status_code=202
        )
    )
    await db.commit()
    return response


@router.post("/callbacks", status_code=202)
async def callback(
    body: Callback,
    request: Request,
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
):
    return await mutation(
        "callbacks", body, db, idempotency_key, x_correlation_id or str(uuid4())
    )


@router.patch("/callbacks/{id}", status_code=202)
async def callback_patch(
    id: str,
    body: Callback,
    request: Request,
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
):
    return await mutation(
        f"callbacks/{id}", body, db, idempotency_key, x_correlation_id or str(uuid4())
    )


@router.post("/transfers/requests", status_code=202)
async def transfer(
    body: Transfer,
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
):
    if body.do_not_call:
        raise HTTPException(403, "do-not-call policy denies transfer")
    if body.campaign_id != "TEST_SYN":
        raise HTTPException(403, "production telephony is disabled")
    return await mutation(
        "transfers/requests",
        body,
        db,
        idempotency_key,
        x_correlation_id or str(uuid4()),
    )


@router.post("/transfers/{id}/{decision}", status_code=202)
async def transfer_decision(
    id: str,
    decision: str,
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
    x_codestra_role: str = Header("", alias="X-Codestra-Role"),
    x_do_not_call: bool = Header(False, alias="X-Do-Not-Call"),
):
    if decision not in ("approve", "deny"):
        raise HTTPException(404, "unknown decision")
    corr = x_correlation_id or str(uuid4())
    allowed, reason = authorize_transfer(
        dnc=x_do_not_call,
        authenticated=True,
        role=x_codestra_role,
        campaign_id="TEST_SYN",
        live_enabled=False,
    )
    db.add(
        TransferPolicyDecision(
            transfer_id=id, allowed=allowed, reason=reason, correlation_id=corr
        )
    )
    await persist(db, "transfer." + decision, id, corr, {"id": id}, allowed, reason)
    await db.commit()
    return {"id": id, "decision": "denied", "reason": reason, "correlation_id": corr}


@router.post("/compliance/events", status_code=202)
async def compliance(
    body: Compliance,
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
):
    return await mutation(
        "compliance/events", body, db, idempotency_key, x_correlation_id or str(uuid4())
    )


@router.post("/ai/recommendations/{id}/{decision}", status_code=202)
async def ai_decision(
    id: str,
    decision: str,
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
):
    if decision not in ("accept", "reject"):
        raise HTTPException(404, "unknown decision")
    return await mutation(
        f"ai/{decision}/{id}",
        Recommendation(recommendation=decision),
        db,
        idempotency_key,
        x_correlation_id or str(uuid4()),
    )


@router.post("/reconciliation/run", status_code=202)
async def reconciliation(
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
):
    return await mutation(
        "reconciliation/run",
        Envelope(),
        db,
        idempotency_key,
        x_correlation_id or str(uuid4()),
    )


@router.get("/reconciliation/status")
async def reconciliation_status(db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(ReconciliationCheckpoint))).scalars().all()
    return {
        "checkpoints": [
            {"source": x.source, "status": x.status, "cursor": x.cursor} for x in rows
        ]
    }
