"""Authenticated, durable Klyrow inbound-mail event ingress."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session

PATH = "/internal/provider-events/klyrow"
router = APIRouter(tags=["klyrow-mail"])


class Attachment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0, le=25_000_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_b64: str = Field(max_length=35_000_000)


class KlyrowInboundEvent(BaseModel):
    model_config = ConfigDict(extra="allow")
    event_id: str = Field(min_length=8, max_length=200)
    source_system: str
    event_type: str
    timestamp: str
    tenant_id: str = Field(min_length=1, max_length=200)
    inbound_id: str = Field(min_length=8, max_length=200)
    provider_event_id: str = Field(min_length=8, max_length=200)
    route_id: str = Field(min_length=1, max_length=200)
    destination_kind: str
    destination_ref: str | None = None
    disposition: str
    recipient: str = Field(min_length=3, max_length=320)
    sender: str = Field(max_length=998)
    subject: str = Field(max_length=998)
    message_id: str | None = Field(default=None, max_length=998)
    in_reply_to: str | None = Field(default=None, max_length=998)
    references: str | None = Field(default=None, max_length=10_000)
    date: str | None = Field(default=None, max_length=200)
    cc: str | None = Field(default=None, max_length=10_000)
    text: str | None = Field(default=None, max_length=10_000_000)
    html: str | None = Field(default=None, max_length=10_000_000)
    attachments: list[Attachment] = Field(default_factory=list, max_length=50)


class KlyrowDeliveryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=8, max_length=200)
    source_system: str
    event_type: str = Field(pattern=r"^klyrow\.email\.(submitted|sent|delivered|deferred|bounced|complained|failed)$")
    event_version: str = Field(pattern=r"^1\.0$")
    occurred_at: str
    tenant_id: str = Field(min_length=1, max_length=200)
    message_id: str = Field(min_length=1, max_length=998)
    provider_message_id: str = Field(min_length=1, max_length=998)
    stream: str = Field(pattern=r"^(transactional|security|system|marketing|bulk)$")
    recipient_reference: str = Field(min_length=8, max_length=200)
    status: str = Field(min_length=1, max_length=80)
    provider: str = Field(pattern=r"^postal$")
    correlation_id: str = Field(min_length=1, max_length=200)
    causation_id: str = Field(min_length=1, max_length=200)
    attempt: int = Field(ge=1, le=100)
    metadata: dict = Field(default_factory=dict)


def _one_header(request: Request, name: str) -> str:
    raw_name = name.lower().encode()
    if sum(1 for key, _ in request.scope.get("headers", []) if key == raw_name) != 1:
        raise HTTPException(401, "missing_or_duplicate_klyrow_header")
    return request.headers[name]


def _authenticate(request: Request, body: bytes, event: KlyrowInboundEvent | KlyrowDeliveryEvent) -> None:
    source = _one_header(request, "X-Source-System")
    timestamp = _one_header(request, "X-Klyrow-Timestamp")
    event_id = _one_header(request, "X-Klyrow-Event-Id")
    supplied = _one_header(request, "X-Klyrow-Signature")
    if (
        source != "klyrow"
        or event.source_system != "klyrow"
        or event.event_type not in {"inbound.received", "klyrow.email.submitted", "klyrow.email.sent", "klyrow.email.delivered", "klyrow.email.deferred", "klyrow.email.bounced", "klyrow.email.complained", "klyrow.email.failed"}
    ):
        raise HTTPException(403, "klyrow_identity_rejected")
    if event_id != event.event_id:
        raise HTTPException(409, "klyrow_event_binding_mismatch")
    try:
        if (
            abs(time.time() - int(timestamp))
            > settings.klyrow_mail_signature_ttl_seconds
        ):
            raise HTTPException(401, "expired_klyrow_signature")
        secret = Path(settings.klyrow_mail_hmac_secret_file).read_bytes().strip()
    except (ValueError, OSError) as exc:
        raise HTTPException(503, "klyrow_authentication_unavailable") from exc
    canonical = timestamp.encode() + b"\n" + event_id.encode() + b"\nklyrow\n" + body
    expected = "sha256=" + hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "invalid_klyrow_signature")


@router.post(PATH, status_code=202)
async def receive_klyrow_mail(
    request: Request, db: AsyncSession = Depends(get_session)
) -> dict:
    if not settings.klyrow_mail_ingress_enabled:
        raise HTTPException(503, "klyrow_mail_ingress_disabled")
    body = await request.body()
    if len(body) > settings.klyrow_mail_request_max_bytes:
        raise HTTPException(413, "klyrow_mail_event_too_large")
    if (
        request.headers.get("content-type", "").split(";", 1)[0].lower()
        != "application/json"
    ):
        raise HTTPException(415, "application_json_required")
    try:
        raw = json.loads(body)
        model = KlyrowInboundEvent if raw.get("event_type") == "inbound.received" else KlyrowDeliveryEvent
        event = model.model_validate(raw)
    except ValueError as exc:
        raise HTTPException(422, "invalid_klyrow_mail_event") from exc
    _authenticate(request, body, event)
    if isinstance(event, KlyrowDeliveryEvent):
        payload_hash = hashlib.sha256(body).hexdigest()
        existing = ((await db.execute(text(
            "SELECT payload_hash,status FROM klyrow_delivery_event_inbox WHERE event_id=:event_id"
        ), {"event_id": event.event_id})).mappings().first())
        if existing:
            if not hmac.compare_digest(existing["payload_hash"], payload_hash):
                raise HTTPException(409, "klyrow_event_replay_conflict")
            if existing["status"] == "complete":
                return {"accepted": True, "duplicate": True, "status": "complete"}
        else:
            await db.execute(text("""INSERT INTO klyrow_delivery_event_inbox
              (event_id,payload_hash,received_at,source,schema_version,tenant_id,message_id,
               provider_message_id,event_type,correlation_id,payload,status,attempts)
              VALUES (:event_id,:hash,now(),'klyrow',:version,:tenant,:message,:provider,
                      :event_type,:correlation,CAST(:payload AS jsonb),'pending',0)"""), {
                "event_id": event.event_id, "hash": payload_hash, "version": event.event_version,
                "tenant": event.tenant_id, "message": event.message_id,
                "provider": event.provider_message_id, "event_type": event.event_type,
                "correlation": event.correlation_id, "payload": json.dumps(event.model_dump()),
            })
            await db.commit()
        await db.execute(text("""INSERT INTO klyrow_delivery_analytics
          (event_id,tenant_id,message_id,event_type,occurred_at)
          VALUES (:event_id,:tenant,:message,:event_type,CAST(:occurred AS timestamptz))
          ON CONFLICT (event_id) DO NOTHING"""), {
            "event_id": event.event_id, "tenant": event.tenant_id, "message": event.message_id,
            "event_type": event.event_type, "occurred": event.occurred_at,
        })
        await db.execute(text("""UPDATE klyrow_delivery_event_inbox
          SET status='complete',attempts=attempts+1,updated_at=now(),last_error=NULL
          WHERE event_id=:event_id"""), {"event_id": event.event_id})
        await db.commit()
        return {"accepted": True, "duplicate": False, "status": "complete"}
    if event.destination_kind not in {"odoo_helpdesk", "odoo_accounting"}:
        raise HTTPException(422, "unsupported_inbound_destination")
    if event.disposition != "ACCEPT":
        raise HTTPException(422, "inbound_message_not_accepted")
    payload_hash = hashlib.sha256(body).hexdigest()
    existing = (
        (
            await db.execute(
                text(
                    "SELECT payload_hash,status FROM klyrow_mail_inbound WHERE event_id=:event_id"
                ),
                {"event_id": event.event_id},
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if not hmac.compare_digest(existing["payload_hash"], payload_hash):
            raise HTTPException(409, "klyrow_event_replay_conflict")
        return {"accepted": True, "duplicate": True, "status": existing["status"]}
    await db.execute(
        text("""INSERT INTO klyrow_mail_inbound
      (event_id,idempotency_key,tenant_id,inbound_id,provider_event_id,recipient,
       destination_kind,destination_ref,payload_hash,payload,status,next_attempt_at)
      VALUES (:event_id,:idem,:tenant,:inbound,:provider,:recipient,:kind,:ref,:hash,
              CAST(:payload AS jsonb),'pending',now())"""),
        {
            "event_id": event.event_id,
            "idem": event.provider_event_id,
            "tenant": event.tenant_id,
            "inbound": event.inbound_id,
            "provider": event.provider_event_id,
            "recipient": event.recipient.lower(),
            "kind": event.destination_kind,
            "ref": event.destination_ref,
            "hash": payload_hash,
            "payload": json.dumps(event.model_dump()),
        },
    )
    await db.commit()
    return {"accepted": True, "duplicate": False, "status": "pending"}
