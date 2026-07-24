"""Fast-ACK VICIdial ingress; PostgreSQL commit is the durability boundary."""
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import SecurityError, payload_hash, verify_ingestion_signature
from app.db.models import AuditEvent, IdempotencyRecord, IntegrationDelivery, IntegrationEvent
from app.db.session import get_session
from app.schemas.registry import Envelope, parse_event

router = APIRouter(prefix="/api/v1/events", tags=["events"])

# Compatibility import for older callers; unlike the previous permissive model,
# this is now the strict canonical envelope.
VicidialEvent = Envelope


def _entity_key(event_type: str, payload: dict) -> str | None:
    for field in ("call_id", "callback_id", "agent_id", "campaign_id"):
        if value := payload.get(field):
            return f"{field}:{value}"
    return None


@router.post("/vicidial", status_code=status.HTTP_202_ACCEPTED)
async def ingest_vicidial(
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    signature: str | None = Header(default=None, alias="X-Signature"),
    timestamp: str | None = Header(default=None, alias="X-Timestamp"),
    client_instance: str | None = Header(default=None, alias="X-Client-Instance-ID"),
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    db: AsyncSession = Depends(get_session),
):
    if not idempotency_key or len(idempotency_key) > 255 or not client_instance:
        raise HTTPException(400, "required request identity is missing or invalid")
    if client_instance not in settings.ingestion_clients:
        raise HTTPException(401, "client identity is not authorized")
    body = await request.body()
    if len(body) > settings.request_max_bytes:
        raise HTTPException(413, "request too large")
    try:
        verify_ingestion_signature(
            body, timestamp or "", signature or "", settings.ingestion_hmac_secret,
            ttl=settings.signature_ttl_seconds,
        )
        envelope, parsed_payload = parse_event(body, settings.enabled_events)
    except SecurityError as exc:
        raise HTTPException(401, "request authentication failed") from exc
    except (ValidationError, ValueError) as exc:
        raise HTTPException(422, "event schema validation failed") from exc
    if envelope.client_instance != client_instance:
        raise HTTPException(401, "client identity mismatch")

    request_hash = payload_hash(body)
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    scope = f"vicidial:{client_instance}"
    corr = x_correlation_id or envelope.correlation_id or str(uuid4())
    # Transaction-scoped advisory lock prevents a concurrent duplicate from
    # creating a second logical persistence set.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
        {"value": f"{scope}:{key_hash}"},
    )
    existing = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope, IdempotencyRecord.key_hash == key_hash
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            await db.rollback()
            raise HTTPException(409, "idempotency key conflict")
        await db.commit()
        result = dict(existing.response)
        response.headers.update({
            "X-Correlation-ID": str(result["correlation_id"]),
            "X-Event-ID": str(result["event_id"]),
            "X-Idempotent-Replay": "true",
            "X-Schema-Version": "1.0",
        })
        return result

    payload = parsed_payload.model_dump(mode="json")
    incoming = IntegrationEvent(
        idempotency_key=key_hash,
        event_type=envelope.event_type,
        schema_version=envelope.schema_version,
        original_event_id=str(envelope.event_id),
        entity_key=_entity_key(envelope.event_type, payload),
        source_system="vicidial",
        correlation_id=corr,
        payload_json=payload,
        payload_hash=request_hash,
        state="accepted",
    )
    db.add(incoming)
    await db.flush()
    for target in ("odoo", "n8n"):
        db.add(IntegrationDelivery(
            event_id=incoming.id, target=target, status="disabled",
            max_attempts=settings.outbox_max_attempts,
        ))
    result = {
        "accepted": True, "event_id": str(incoming.id),
        "status": "accepted", "correlation_id": corr,
    }
    db.add(IdempotencyRecord(
        scope=scope, key_hash=key_hash, request_hash=request_hash,
        response=result, status_code=202, event_id=incoming.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    ))
    db.add(AuditEvent(
        action="vicidial.event.accepted", subject=str(incoming.id),
        correlation_id=corr, decision="accepted",
        redacted_payload={"event_type": envelope.event_type, "schema_version": "1.0"},
    ))
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(503, "durable persistence unavailable")
    response.headers.update({
        "X-Correlation-ID": corr,
        "X-Event-ID": str(incoming.id),
        "X-Idempotent-Replay": "false",
        "X-Schema-Version": "1.0",
    })
    return result
