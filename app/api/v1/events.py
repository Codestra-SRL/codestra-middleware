import hashlib
import json
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.config import settings
from app.core.policy import PolicyError, enforce_test_campaign
from app.core.security import SecurityError, payload_hash, verify_ingestion_signature
from app.db.models import IdempotencyRecord, IntegrationDelivery, IntegrationEvent
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/events", tags=["events"])


class VicidialEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    uniqueid: str = Field(min_length=1, max_length=128)
    lead_id: int
    campaign_id: str = Field(min_length=1, max_length=64)


@router.post("/vicidial", status_code=status.HTTP_202_ACCEPTED)
async def ingest_vicidial(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    signature: str | None = Header(default=None, alias="X-Signature"),
    timestamp: str | None = Header(default=None, alias="X-Timestamp"),
    client_instance: str | None = Header(default=None, alias="X-Client-Instance-ID"),
    db: AsyncSession = Depends(get_session),
):
    if not idempotency_key or not client_instance:
        raise HTTPException(
            400, "Idempotency-Key and X-Client-Instance-ID are required"
        )
    body = await request.body()
    if len(body) > settings.request_max_bytes:
        raise HTTPException(413, "request too large")
    try:
        verify_ingestion_signature(
            body,
            timestamp or "",
            signature or "",
            settings.webhook_shared_secret,
            ttl=settings.signature_ttl_seconds,
        )
        event = VicidialEvent.model_validate_json(body)
        enforce_test_campaign(event.model_dump())
    except (SecurityError, PolicyError, ValueError) as exc:
        raise HTTPException(
            401 if isinstance(exc, SecurityError) else 422, str(exc)
        ) from exc
    canonical = json.dumps(
        event.model_dump(), sort_keys=True, separators=(",", ":")
    ).encode()
    request_hash = payload_hash(canonical)
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    scope = f"vicidial:{client_instance}"
    existing = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope, IdempotencyRecord.key_hash == key_hash
        )
    )
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(409, "idempotency key conflict")
        return existing.response
    incoming = IntegrationEvent(
        event_type="vicidial",
        campaign_id=event.campaign_id,
        payload=event.model_dump(),
        payload_hash=request_hash,
    )
    db.add(incoming)
    await db.flush()
    db.add(IntegrationDelivery(event_id=incoming.id, target="odoo"))
    response = {"accepted": True, "event_id": str(incoming.id), "status": "queued"}
    db.add(
        IdempotencyRecord(
            scope=scope,
            key_hash=key_hash,
            request_hash=request_hash,
            response=response,
            status_code=202,
            event_id=incoming.id,
        )
    )
    await db.commit()
    return response
