"""Authenticated durable n8n execution registration and acknowledgement."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automation import (
    AutomationSecurityError,
    canonical_hash,
    verify_exact_body,
    verify_timestamp,
)
from app.core.config import settings
from app.db.models import (
    AuditEvent,
    BroadEventDelivery,
    IntegrationEvent,
    N8nAcknowledgement,
    N8nExecutionRegistration,
    OutboxEvent,
    PublisherNonce,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/n8n", tags=["n8n-production-transport"])


class ExecutionRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    delivery_id: UUID
    event_id: str = Field(min_length=1, max_length=128)
    workflow_id: str = Field(min_length=1, max_length=128)
    workflow_version: str = Field(min_length=1, max_length=128)
    execution_id: str = Field(min_length=1, max_length=128)
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment: Literal["production"]
    accepted_at: datetime


class AcknowledgementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    acknowledgement_id: UUID
    delivery_id: UUID
    event_id: str = Field(min_length=1, max_length=128)
    workflow_id: str = Field(min_length=1, max_length=128)
    workflow_version: str = Field(min_length=1, max_length=128)
    execution_id: str = Field(min_length=1, max_length=128)
    execution_status: Literal["SUCCEEDED", "FAILED", "DEAD_LETTERED"]
    result_classification: str = Field(min_length=1, max_length=64)
    result_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: datetime
    completed_at: datetime
    attempt_number: int = Field(ge=1)
    correlation_id: str = Field(min_length=1, max_length=128)
    policy_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


async def authenticate(
    request: Request,
    db: AsyncSession,
    timestamp: str,
    nonce: str,
    signature: str,
    key_id: str,
) -> bytes:
    body = await request.body()
    try:
        verify_timestamp(timestamp, ttl_seconds=settings.signature_ttl_seconds)
        verify_exact_body(body, signature, settings.webhook_shared_secret)
    except AutomationSecurityError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    if key_id != "codestra-n8n-production" or not nonce or len(nonce) > 128:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid service identity")
    existing = await db.get(PublisherNonce, (key_id, nonce))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "replayed request")
    now = datetime.now(UTC)
    db.add(
        PublisherNonce(
            key_id=key_id,
            nonce=nonce,
            signed_at=int(timestamp),
            expires_at=now + timedelta(seconds=settings.signature_ttl_seconds),
        )
    )
    return body


@router.post("/executions/register", status_code=202)
async def register_execution(
    request: Request,
    x_codestra_timestamp: str = Header(alias="X-Codestra-Timestamp"),
    x_codestra_nonce: str = Header(alias="X-Codestra-Nonce"),
    x_codestra_key_id: str = Header(alias="X-Codestra-Key-ID"),
    x_codestra_signature: str = Header(alias="X-Codestra-Signature"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    raw = await authenticate(
        request,
        db,
        x_codestra_timestamp,
        x_codestra_nonce,
        x_codestra_signature,
        x_codestra_key_id,
    )
    try:
        body = ExecutionRegistrationRequest.model_validate_json(raw)
    except ValueError as exc:
        raise HTTPException(422, "invalid execution registration") from exc
    delivery = await db.get(BroadEventDelivery, body.delivery_id, with_for_update=True)
    if delivery is None:
        raise HTTPException(404, "delivery not found")
    event = await db.get(IntegrationEvent, delivery.event_id)
    expected = (
        event is not None
        and event.original_event_id == body.event_id
        and delivery.workflow_id == body.workflow_id
        and delivery.workflow_version == body.workflow_version
        and delivery.payload_hash == body.payload_hash
        and delivery.target_environment == body.environment
        and delivery.status in {"SUBMITTED", "ACCEPTED", "EXECUTION_REGISTERED"}
    )
    if not expected:
        await db.rollback()
        raise HTTPException(409, "execution registration binding mismatch")
    prior = await db.scalar(
        select(N8nExecutionRegistration).where(
            N8nExecutionRegistration.delivery_id == body.delivery_id
        )
    )
    if prior:
        if prior.execution_id != body.execution_id:
            await db.rollback()
            raise HTTPException(409, "execution registration conflict")
        await db.commit()
        return {
            "schema_version": "1.0",
            "delivery_id": str(body.delivery_id),
            "event_id": body.event_id,
            "workflow_id": body.workflow_id,
            "workflow_version": body.workflow_version,
            "execution_registration_id": str(prior.execution_registration_id),
            "execution_id_or_pending_reference": prior.execution_id,
            "idempotency_status": "duplicate",
            "accepted_at": prior.accepted_at.isoformat(),
            "response_hash": prior.response_hash,
        }
    response_hash = canonical_hash(body.model_dump(mode="json"))
    registration = N8nExecutionRegistration(
        delivery_id=body.delivery_id,
        event_id=body.event_id,
        workflow_id=body.workflow_id,
        workflow_version=body.workflow_version,
        execution_id=body.execution_id,
        payload_hash=body.payload_hash,
        environment=body.environment,
        status="REGISTERED",
        accepted_at=body.accepted_at,
        response_hash=response_hash,
    )
    db.add(registration)
    delivery.status = "EXECUTION_REGISTERED"
    delivery.response_received_at = datetime.now(UTC)
    delivery.response_hash = response_hash
    await db.commit()
    return {
        "schema_version": "1.0",
        "delivery_id": str(body.delivery_id),
        "event_id": body.event_id,
        "workflow_id": body.workflow_id,
        "workflow_version": body.workflow_version,
        "execution_registration_id": str(registration.execution_registration_id),
        "execution_id_or_pending_reference": body.execution_id,
        "idempotency_status": "created",
        "accepted_at": body.accepted_at.isoformat(),
        "response_hash": response_hash,
    }


@router.post("/acknowledgements", status_code=202)
async def acknowledge_execution(
    request: Request,
    x_codestra_timestamp: str = Header(alias="X-Codestra-Timestamp"),
    x_codestra_nonce: str = Header(alias="X-Codestra-Nonce"),
    x_codestra_key_id: str = Header(alias="X-Codestra-Key-ID"),
    x_codestra_signature: str = Header(alias="X-Codestra-Signature"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    raw = await authenticate(
        request,
        db,
        x_codestra_timestamp,
        x_codestra_nonce,
        x_codestra_signature,
        x_codestra_key_id,
    )
    try:
        body = AcknowledgementRequest.model_validate_json(raw)
    except ValueError as exc:
        raise HTTPException(422, "invalid acknowledgement") from exc
    delivery = await db.get(BroadEventDelivery, body.delivery_id, with_for_update=True)
    registration = await db.scalar(
        select(N8nExecutionRegistration).where(
            N8nExecutionRegistration.delivery_id == body.delivery_id
        )
    )
    event = await db.get(IntegrationEvent, delivery.event_id) if delivery else None
    if (
        delivery is None
        or registration is None
        or event is None
        or event.original_event_id != body.event_id
        or delivery.workflow_id != body.workflow_id
        or delivery.workflow_version != body.workflow_version
        or delivery.policy_hash != body.policy_hash
        or delivery.attempt_number != body.attempt_number
        or registration.execution_id != body.execution_id
        or body.completed_at < body.started_at
    ):
        await db.rollback()
        raise HTTPException(409, "acknowledgement binding mismatch")
    prior = await db.scalar(
        select(N8nAcknowledgement).where(
            (N8nAcknowledgement.acknowledgement_id == body.acknowledgement_id)
            | (N8nAcknowledgement.delivery_id == body.delivery_id)
        )
    )
    if prior:
        if (
            prior.acknowledgement_id != body.acknowledgement_id
            or prior.event_id != body.event_id
            or prior.execution_id != body.execution_id
            or prior.result_hash != body.result_hash
        ):
            await db.rollback()
            raise HTTPException(409, "acknowledgement conflict")
        await db.commit()
        return {
            "acknowledgement_id": str(prior.acknowledgement_id),
            "delivery_id": str(prior.delivery_id),
            "event_id": prior.event_id,
            "persisted": True,
            "final_delivery_status": delivery.status,
            "persisted_at": prior.persisted_at.isoformat(),
            "response_hash": canonical_hash(body.model_dump(mode="json")),
        }
    if delivery.status != "EXECUTION_REGISTERED":
        await db.rollback()
        raise HTTPException(409, "delivery is not execution registered")
    now = datetime.now(UTC)
    acknowledgement = N8nAcknowledgement(**body.model_dump(exclude={"schema_version"}))
    db.add(acknowledgement)
    registration.status = body.execution_status
    delivery.status = (
        "ACKNOWLEDGED"
        if body.execution_status == "SUCCEEDED"
        else "RECONCILIATION_REQUIRED"
    )
    delivery.acknowledged_at = now
    result = body.model_dump(mode="json")
    db.add(
        OutboxEvent(
            topic="odoo.integration.result",
            payload=result,
            correlation_id=body.correlation_id,
            status="pending",
            attempts=0,
        )
    )
    db.add(
        AuditEvent(
            action="n8n.acknowledgement.persisted",
            subject=body.event_id,
            correlation_id=body.correlation_id,
            decision=body.execution_status,
            redacted_payload={
                "delivery_id": str(body.delivery_id),
                "workflow_id": body.workflow_id,
                "execution_id": body.execution_id,
                "result_hash": body.result_hash,
            },
        )
    )
    await db.commit()
    return {
        "acknowledgement_id": str(body.acknowledgement_id),
        "delivery_id": str(body.delivery_id),
        "event_id": body.event_id,
        "persisted": True,
        "final_delivery_status": delivery.status,
        "persisted_at": acknowledgement.persisted_at.isoformat(),
        "response_hash": canonical_hash(result),
    }


@router.get("/deliveries/{event_id}")
async def delivery_status(
    event_id: str, db: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    registration = await db.scalar(
        select(N8nExecutionRegistration)
        .join(BroadEventDelivery)
        .join(IntegrationEvent)
        .where(IntegrationEvent.original_event_id == event_id)
    )
    if registration is None:
        return {"event_id": event_id, "status": "NOT_FOUND"}
    return {"event_id": event_id, "status": registration.status}
