"""Contract-v2 receiver: commit event, replay nonce, and acknowledgement together."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.publisher_auth import (
    PublisherAuthenticationError, verify_publisher_request,
)
from app.db.models import (
    IntegrationEvent, PublisherAcknowledgement, PublisherNonce,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v2/telephony", tags=["telephony-publisher"])


def ack(event_id, status, duplicate, retryable, reason_code, acknowledgement_id=None):
    return {
        "schema_version": "2.0", "event_id": event_id,
        "acknowledgement_id": str(acknowledgement_id or uuid4()),
        "receiver_timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status, "duplicate": duplicate, "retryable": retryable,
        "reason_code": reason_code,
    }


def validate_event(value):
    required = {
        "schema_version", "event_id", "event_type", "source_system", "created_at",
        "occurred_at", "boot_session_id", "sequence", "call_uniqueid",
        "correlation_id", "business_unit", "campaign", "agent_id",
        "customer_reference", "payload", "policy_decision", "recording_reference",
        "delivery", "privacy", "idempotency",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("schema_rejected")
    if value["schema_version"] != "2.0":
        raise ValueError("schema_rejected")
    UUID(value["event_id"])
    if value["event_type"] != "synthetic.publisher_canary":
        raise PermissionError("policy_rejected")
    privacy = value["privacy"]
    if privacy != {"classification": "synthetic", "contains_customer_data": False}:
        raise PermissionError("policy_rejected")
    expires = datetime.fromisoformat(value["delivery"]["expires_at"].replace("Z", "+00:00"))
    if expires <= datetime.now(timezone.utc):
        raise PermissionError("policy_rejected")
    if value["campaign"] != "TEST_SYN":
        raise PermissionError("policy_rejected")


@router.post("/canary", status_code=202)
async def receive_canary(request: Request, db: AsyncSession = Depends(get_session)):
    if not settings.publisher_canary_enabled:
        raise HTTPException(404, "canary route disabled")
    body = await request.body()
    try:
        key_id, nonce, signed_at, header_event_id = verify_publisher_request(
            body, request.headers, settings.publisher_hmac_keys,
            window=settings.signature_ttl_seconds,
        )
    except PublisherAuthenticationError as exc:
        raise HTTPException(401, "request authentication failed") from exc
    replay = await db.scalar(
        select(PublisherNonce).where(
            PublisherNonce.key_id == key_id, PublisherNonce.nonce == nonce
        )
    )
    if replay:
        raise HTTPException(401, "request replay rejected")
    db.add(PublisherNonce(
        key_id=key_id, nonce=nonce, signed_at=signed_at,
        expires_at=datetime.now(timezone.utc),
    ))
    try:
        value = json.loads(body)
        validate_event(value)
        if value["event_id"] != header_event_id:
            raise ValueError("schema_rejected")
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(422, "schema_rejected") from exc
    digest = hashlib.sha256(body).hexdigest()
    event_id = value["event_id"]
    existing = await db.scalar(
        select(IntegrationEvent).where(IntegrationEvent.original_event_id == event_id)
    )
    if existing:
        if existing.payload_hash != digest:
            raise HTTPException(409, "idempotency_conflict")
        prior = await db.scalar(
            select(PublisherAcknowledgement).where(
                PublisherAcknowledgement.event_id == event_id
            )
        )
        result = ack(event_id, "duplicate", True, False, "already_accepted",
                     prior.acknowledgement_id if prior else None)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(401, "request replay rejected") from exc
        return result
    acknowledgement_id = uuid4()
    result = ack(event_id, "accepted", False, False, "durably_accepted",
                 acknowledgement_id)
    incoming = IntegrationEvent(
        idempotency_key=value["idempotency"]["key"],
        event_type=value["event_type"], schema_version="2.0",
        original_event_id=event_id, entity_key="synthetic:publisher-canary",
        source_system="asterisk-ami", correlation_id=value["correlation_id"],
        payload_json=value, payload_hash=digest, state="accepted",
    )
    db.add(incoming)
    db.add(PublisherAcknowledgement(
        acknowledgement_id=acknowledgement_id, event_id=event_id,
        status="accepted", duplicate=False, retryable=False,
        reason_code="durably_accepted", acknowledgement=result,
    ))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(401, "request replay rejected") from exc
    except Exception as exc:
        await db.rollback()
        raise HTTPException(503, "durable persistence unavailable") from exc
    return result
