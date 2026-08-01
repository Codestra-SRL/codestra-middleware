"""Durable n8n ingress and terminal lifecycle callbacks.

The routes are intentionally boring: every transition is authenticated, scoped,
idempotent, and recorded before an acknowledgement is returned.
"""
from datetime import UTC, datetime
import hmac
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automation import canonical_hash, redact, verify_exact_body, verify_timestamp
from app.core.config import settings
from app.db.models import (
    IntegrationDelivery, IntegrationEvent, IntegrationResult, IntegrationTrace, OutboxEvent,
    N8nAcknowledgement, N8nExecution,
)
from app.db.session import get_session

router = APIRouter(tags=["n8n-lifecycle"])


class ExecutionRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=16, max_length=255)
    originating_odoo_outbox_id: str = Field(min_length=1, max_length=128)
    originating_middleware_outbox_id: str = Field(min_length=1, max_length=128)
    workflow_key: str = Field(pattern=r"^(?:WF|N8)-[A-Za-z0-9_.-]+$")
    workflow_version: str = Field(min_length=1, max_length=32)
    status: Literal["REGISTERED", "RUNNING"] = "REGISTERED"
    details: dict[str, Any] = Field(default_factory=dict)


class N8nIngressEnvelope(BaseModel):
    """Canonical generic webhook contract used by the n8n package."""
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=128)
    event_type: Literal[
        "call.completed", "callback.due", "lead.enrichment_requested",
        "lead.hot", "report.daily_requested",
    ]
    event_version: Literal["1.0"]
    occurred_at: datetime
    received_at: datetime
    tenant_id: str = Field(min_length=1, max_length=128)
    environment: Literal["test", "staging"]
    request_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=255)
    source: str = Field(min_length=1, max_length=64)
    campaign_id: str = Field(min_length=1, max_length=64)
    originating_odoo_outbox_id: str = Field(min_length=1, max_length=128)
    originating_middleware_outbox_id: str = Field(min_length=1, max_length=128)
    synthetic: bool
    references: dict[str, Any] = Field(default_factory=dict)
    data: dict[str, Any] = Field(default_factory=dict)


class N8nVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: N8nIngressEnvelope
    source_headers: dict[str, str]


class Acknowledgement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    status: Literal["SUCCEEDED", "FAILED", "RETRY", "DEAD_LETTERED"]
    payload: dict[str, Any] = Field(default_factory=dict)


class ResultCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"]
    execution_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=16, max_length=255)
    event_type: Literal["lead.hot"]
    environment: Literal["staging"]
    originating_odoo_outbox_id: str = Field(min_length=1, max_length=128)
    originating_middleware_outbox_id: str = Field(min_length=1, max_length=128)
    created_at: datetime
    completed_at: datetime
    synthetic: Literal[True]
    terminal_status: Literal["SUCCEEDED", "FAILED", "DEAD_LETTERED"]
    result: dict[str, Any] | None = None
    bounded_error: dict[str, Any] | None = None

    @model_validator(mode="after")
    def terminal_body(self):
        if self.terminal_status == "SUCCEEDED" and self.result is None:
            raise ValueError("successful result body is required")
        if self.terminal_status != "SUCCEEDED" and self.bounded_error is None:
            raise ValueError("bounded terminal error is required")
        return self


class InternalHotLeadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=16, max_length=255)
    event_type: Literal["lead.hot"]
    environment: Literal["staging"]
    synthetic: Literal[True]
    result: dict[str, Any] = Field(default_factory=dict)


class FailureCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execution_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=16, max_length=255)
    originating_odoo_outbox_id: str = Field(min_length=1, max_length=128)
    originating_middleware_outbox_id: str = Field(min_length=1, max_length=128)
    environment: Literal["staging"]
    synthetic: Literal[True]
    attempt: int = Field(ge=1, le=5)
    error_code: str = Field(min_length=1, max_length=64)
    error_summary: str = Field(min_length=1, max_length=512)


async def _trace(db: AsyncSession, correlation_id: str, stage: str, identity: str,
                 state: str, details: dict[str, Any] | None = None) -> None:
    existing = await db.scalar(select(IntegrationTrace).where(
        IntegrationTrace.correlation_id == correlation_id,
        IntegrationTrace.stage == stage,
        IntegrationTrace.identity == identity,
    ))
    if not existing:
        db.add(IntegrationTrace(correlation_id=correlation_id, stage=stage,
                                identity=identity, status=state,
                                details=redact(details or {})))


async def _bound_event(
    db: AsyncSession,
    *,
    event_id: str,
    correlation_id: str,
    originating_odoo_outbox_id: str,
    originating_middleware_outbox_id: str,
) -> tuple[IntegrationEvent, OutboxEvent]:
    event = await db.scalar(
        select(IntegrationEvent).where(
            IntegrationEvent.original_event_id == event_id
        )
    )
    if not event:
        raise HTTPException(422, "event must be persisted before lifecycle activity")
    if (
        event.correlation_id != correlation_id
        or event.environment != "staging"
        or event.originating_odoo_outbox_id != originating_odoo_outbox_id
    ):
        raise HTTPException(409, "immutable event binding mismatch")
    outbox = await db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.integration_event_id == event.id,
            OutboxEvent.topic == "event.accepted",
        )
    )
    if not outbox or str(outbox.id) != originating_middleware_outbox_id:
        raise HTTPException(409, "immutable Middleware outbox binding mismatch")
    return event, outbox


async def require_n8n_internal_auth(request: Request) -> None:
    """Fail closed unless the protected n8n staging credential is present."""
    expected = settings.n8n_internal_auth_token
    header = settings.n8n_internal_auth_header
    supplied = request.headers.get(header) if header else None
    if not expected or not header or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(401, "invalid internal authentication")


@router.post("/api/v1/automation/events/verify")
async def verify_n8n_event(
    body: N8nVerificationRequest,
    _: None = Depends(require_n8n_internal_auth),
) -> dict[str, Any]:
    """Verify middleware signature and staging scope without persisting the event."""
    source_headers = {key.lower(): value for key, value in body.source_headers.items()}
    signature = source_headers.get("x-codestra-signature", "")
    timestamp = source_headers.get("x-codestra-timestamp", "")
    event_id = source_headers.get("x-codestra-event-id", "")
    workflow_id = source_headers.get("x-codestra-workflow-id", "")
    raw = json.dumps(
        body.event.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    try:
        verify_timestamp(timestamp, ttl_seconds=settings.signature_ttl_seconds)
        verify_exact_body(raw, signature, settings.outbox_signature_secret)
    except Exception as exc:
        raise HTTPException(401, "invalid event authentication") from exc
    if event_id != body.event.event_id:
        raise HTTPException(422, "event identifier mismatch")
    if not workflow_id.startswith(("WF-", "N8-")):
        raise HTTPException(403, "workflow not permitted")
    if body.event.environment != settings.automation_environment:
        raise HTTPException(403, "environment not permitted")
    if body.event.campaign_id not in settings.allowed_campaigns:
        raise HTTPException(403, "campaign not permitted")
    return {"accepted": True, "verified": True, **body.event.model_dump(mode="json")}


@router.get("/api/v1/integration/events/{event_id}/context")
async def canonical_event_context(
    event_id: str,
    correlation_id: str,
    originating_odoo_outbox_id: str,
    originating_middleware_outbox_id: str,
    _: None = Depends(require_n8n_internal_auth),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    event, _ = await _bound_event(
        db,
        event_id=event_id,
        correlation_id=correlation_id,
        originating_odoo_outbox_id=originating_odoo_outbox_id,
        originating_middleware_outbox_id=originating_middleware_outbox_id,
    )
    return {
        "event_id": event.original_event_id,
        "correlation_id": event.correlation_id,
        "idempotency_key": event.idempotency_key,
        "event_type": event.event_type,
        "environment": event.environment,
        "originating_odoo_outbox_id": event.originating_odoo_outbox_id,
        "originating_middleware_outbox_id": originating_middleware_outbox_id,
        "synthetic": bool(event.payload_json.get("synthetic")),
        "references": event.payload_json.get("references", {}),
        "data": event.payload_json.get("data", {}),
    }


@router.post("/webhook/v1/events", status_code=status.HTTP_202_ACCEPTED)
async def generic_ingress(
    request: Request,
    x_codestra_event_id: str = Header(alias="X-Codestra-Event-ID"),
    x_codestra_workflow_id: str = Header(alias="X-Codestra-Workflow-ID"),
    x_codestra_timestamp: str = Header(alias="X-Codestra-Timestamp"),
    x_codestra_signature: str = Header(alias="X-Codestra-Signature"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    raw = await request.body()
    try:
        verify_timestamp(x_codestra_timestamp, ttl_seconds=settings.signature_ttl_seconds)
        verify_exact_body(raw, x_codestra_signature, settings.webhook_shared_secret)
        envelope = N8nIngressEnvelope.model_validate_json(raw)
    except Exception as exc:
        # Do not expose schema details on the signed boundary.
        if type(exc).__name__ == "AutomationSecurityError":
            raise HTTPException(401, "invalid webhook authentication") from exc
        raise HTTPException(422, "invalid event schema") from exc
    if envelope.event_id != x_codestra_event_id:
        raise HTTPException(422, "event identifier mismatch")
    if not x_codestra_workflow_id.startswith(("WF-", "N8-")):
        raise HTTPException(403, "workflow not permitted")
    if envelope.environment != settings.automation_environment:
        raise HTTPException(403, "environment not permitted")
    if envelope.campaign_id not in settings.allowed_campaigns:
        raise HTTPException(403, "campaign not permitted")
    event, _ = await _bound_event(
        db,
        event_id=envelope.event_id,
        correlation_id=envelope.correlation_id,
        originating_odoo_outbox_id=envelope.originating_odoo_outbox_id,
        originating_middleware_outbox_id=envelope.originating_middleware_outbox_id,
    )
    if event.idempotency_key != envelope.idempotency_key:
        raise HTTPException(409, "idempotency binding mismatch")
    return {
        "accepted": True,
        "event_id": envelope.event_id,
        "correlation_id": envelope.correlation_id,
        "status": "already_persisted",
    }


async def _execution(db: AsyncSession, body: ExecutionRegistration) -> tuple[N8nExecution, bool]:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:registration_key))"),
        {"registration_key": f"{body.event_id}:{body.workflow_key}"},
    )
    row = await db.scalar(select(N8nExecution).where(N8nExecution.execution_id == body.execution_id).with_for_update())
    request_hash = canonical_hash(body.model_dump(mode="json"))
    if row:
        if row.registration_hash != request_hash:
            raise HTTPException(409, "conflicting execution registration")
        return row, True
    event, _ = await _bound_event(
        db,
        event_id=body.event_id,
        correlation_id=body.correlation_id,
        originating_odoo_outbox_id=body.originating_odoo_outbox_id,
        originating_middleware_outbox_id=body.originating_middleware_outbox_id,
    )
    if event.idempotency_key != body.idempotency_key:
        raise HTTPException(409, "idempotency binding mismatch")
    row = N8nExecution(execution_id=body.execution_id, event_id=body.event_id,
                       workflow_key=body.workflow_key, workflow_version=body.workflow_version,
                       correlation_id=body.correlation_id, status=body.status,
                       registration_hash=request_hash, details=redact(body.details))
    db.add(row)
    await _trace(db, body.correlation_id, "N8N_EXECUTION_REGISTERED", body.execution_id, body.status)
    return row, False


@router.post("/api/v1/n8n/executions", status_code=status.HTTP_202_ACCEPTED)
async def register_execution(body: ExecutionRegistration, _: None = Depends(require_n8n_internal_auth), db: AsyncSession = Depends(get_session)):
    try:
        row, duplicate = await _execution(db, body)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "concurrent execution registration conflict") from exc
    return {"accepted": True, "execution_id": row.execution_id, "event_id": row.event_id, "correlation_id": row.correlation_id, "duplicate": duplicate}


@router.post("/api/v1/n8n/acknowledgements", status_code=status.HTTP_202_ACCEPTED)
async def acknowledge(body: Acknowledgement, _: None = Depends(require_n8n_internal_auth), db: AsyncSession = Depends(get_session)):
    execution = await db.scalar(select(N8nExecution).where(N8nExecution.execution_id == body.execution_id).with_for_update())
    if not execution:
        raise HTTPException(422, "execution registration required")
    if execution.event_id != body.event_id or execution.correlation_id != body.correlation_id:
        raise HTTPException(409, "acknowledgement binding mismatch")
    digest = canonical_hash(body.model_dump(mode="json"))
    prior = await db.scalar(select(N8nAcknowledgement).where(N8nAcknowledgement.execution_id == body.execution_id).with_for_update())
    if prior:
        if prior.acknowledgement_hash != digest:
            raise HTTPException(409, "conflicting acknowledgement")
        await db.commit()
        return {"accepted": True, "duplicate": True, "acknowledgement_id": str(prior.acknowledgement_id)}
    db.add(N8nAcknowledgement(execution_id=body.execution_id, event_id=body.event_id,
                              correlation_id=body.correlation_id, status=body.status,
                              acknowledgement_hash=digest, payload=redact(body.payload)))
    execution.status = body.status if body.status in {"SUCCEEDED", "FAILED", "CANCELLED"} else "RUNNING"
    execution.completed_at = datetime.now(UTC) if body.status in {"SUCCEEDED", "FAILED", "DEAD_LETTERED"} else None
    await _trace(db, body.correlation_id, "N8N_ACKNOWLEDGED", body.execution_id, body.status)
    await db.commit()
    return {"accepted": True, "duplicate": False, "execution_id": body.execution_id, "status": body.status}


@router.post("/api/v1/n8n/internal-results", status_code=status.HTTP_202_ACCEPTED)
async def internal_hot_lead_result(
    body: InternalHotLeadResult,
    _: None = Depends(require_n8n_internal_auth),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    execution = await db.scalar(
        select(N8nExecution).where(N8nExecution.execution_id == body.execution_id)
    )
    if (
        not execution
        or execution.event_id != body.event_id
        or execution.correlation_id != body.correlation_id
    ):
        raise HTTPException(409, "internal result binding mismatch")
    event = await db.scalar(
        select(IntegrationEvent).where(
            IntegrationEvent.original_event_id == body.event_id
        )
    )
    if (
        not event
        or event.event_type != body.event_type
        or event.environment != body.environment
        or event.idempotency_key != body.idempotency_key
        or not body.synthetic
    ):
        raise HTTPException(409, "internal result event mismatch")
    await _trace(
        db, body.correlation_id, "HOT_LEAD_INTERNAL_RESULT", body.execution_id,
        "RECORDED", {"result": redact(body.result), "external_delivery": False},
    )
    await db.commit()
    return {
        "accepted": True,
        "event_id": body.event_id,
        "correlation_id": body.correlation_id,
        "external_delivery": False,
    }


@router.post("/api/v1/n8n/failures", status_code=status.HTTP_202_ACCEPTED)
async def park_failure(
    body: FailureCallback,
    _: None = Depends(require_n8n_internal_auth),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    execution = await db.scalar(
        select(N8nExecution)
        .where(N8nExecution.execution_id == body.execution_id)
        .with_for_update()
    )
    if not execution:
        raise HTTPException(422, "execution registration required")
    event, _ = await _bound_event(
        db,
        event_id=body.event_id,
        correlation_id=body.correlation_id,
        originating_odoo_outbox_id=body.originating_odoo_outbox_id,
        originating_middleware_outbox_id=body.originating_middleware_outbox_id,
    )
    if event.idempotency_key != body.idempotency_key:
        raise HTTPException(409, "failure idempotency mismatch")
    bounded = {
        "error_code": body.error_code,
        "error_summary": body.error_summary,
        "attempt": body.attempt,
    }
    digest = canonical_hash(bounded)
    prior = await db.scalar(
        select(N8nAcknowledgement).where(
            N8nAcknowledgement.execution_id == body.execution_id
        )
    )
    if prior:
        if prior.status != "DEAD_LETTERED" or prior.acknowledgement_hash != digest:
            raise HTTPException(409, "conflicting terminal failure")
        return {"accepted": True, "duplicate": True, "status": "DEAD_LETTERED"}
    db.add(
        N8nAcknowledgement(
            execution_id=body.execution_id,
            event_id=body.event_id,
            correlation_id=body.correlation_id,
            status="DEAD_LETTERED",
            acknowledgement_hash=digest,
            payload=redact(bounded),
        )
    )
    execution.status = "DEAD_LETTERED"
    execution.completed_at = datetime.now(UTC)
    event.state = "dead_lettered"
    await _trace(
        db, body.correlation_id, "N8N_DEAD_LETTERED", body.execution_id,
        "DEAD_LETTERED", bounded,
    )
    await db.commit()
    return {"accepted": True, "duplicate": False, "status": "DEAD_LETTERED"}


@router.post("/api/v1/n8n/results", status_code=status.HTTP_202_ACCEPTED)
async def result_callback(body: ResultCallback, _: None = Depends(require_n8n_internal_auth), db: AsyncSession = Depends(get_session)):
    execution = await db.scalar(select(N8nExecution).where(N8nExecution.execution_id == body.execution_id).with_for_update())
    if not execution or execution.event_id != body.event_id or execution.correlation_id != body.correlation_id:
        raise HTTPException(409, "result binding mismatch")
    event, middleware_outbox = await _bound_event(
        db,
        event_id=body.event_id,
        correlation_id=body.correlation_id,
        originating_odoo_outbox_id=body.originating_odoo_outbox_id,
        originating_middleware_outbox_id=body.originating_middleware_outbox_id,
    )
    if body.idempotency_key != f"result:{body.execution_id}:{body.event_id}":
        raise HTTPException(409, "result idempotency mismatch")
    if event.event_type != body.event_type or event.environment != body.environment:
        raise HTTPException(409, "result event scope mismatch")
    terminal_payload = redact(body.result if body.result is not None else {"error": body.bounded_error})
    prior = await db.scalar(select(IntegrationResult).where(IntegrationResult.idempotency_key == body.idempotency_key).with_for_update())
    if prior:
        if prior.execution_id != body.execution_id or prior.payload != terminal_payload:
            raise HTTPException(409, "conflicting duplicate result")
        await db.commit()
        return {"accepted": True, "duplicate": True, "result_id": str(prior.result_id)}
    result = IntegrationResult(execution_id=body.execution_id, event_id=body.event_id,
                               correlation_id=body.correlation_id, idempotency_key=body.idempotency_key,
                               status=body.terminal_status, payload=terminal_payload)
    db.add(result)
    await db.flush()
    delivery = await db.scalar(select(IntegrationDelivery).join(IntegrationEvent, IntegrationEvent.id == IntegrationDelivery.event_id).where(
        IntegrationEvent.original_event_id == body.event_id, IntegrationDelivery.target == "odoo"))
    if delivery:
        delivery.status = "pending" if settings.odoo_delivery_enabled else "disabled"
        delivery.result_json = terminal_payload
    acknowledgement = await db.scalar(
        select(N8nAcknowledgement).where(
            N8nAcknowledgement.execution_id == body.execution_id
        )
    )
    if not acknowledgement:
        raise HTTPException(422, "terminal acknowledgement required before result")
    references = event.payload_json.get("references", {})
    business_unit = str(references.get("business_unit_public_id") or "")
    if not business_unit:
        raise HTTPException(422, "stored business-unit binding is required")
    odoo_payload = {
        "schema_version": body.schema_version,
        "result_public_id": str(result.result_id),
        "delivery_id": str(delivery.id) if delivery else str(result.result_id),
        "event_id": body.event_id,
        "registration_id": str(execution.id),
        "acknowledgement_id": str(acknowledgement.acknowledgement_id),
        "correlation_id": body.correlation_id,
        "idempotency_key": body.idempotency_key,
        "execution_id": body.execution_id,
        "event_type": body.event_type,
        "terminal_status": body.terminal_status,
        "execution_status": body.terminal_status,
        "result_hash": f"sha256:{canonical_hash(terminal_payload)}",
        "originating_outbox_public_id": event.originating_odoo_outbox_id,
        "originating_middleware_outbox_id": str(middleware_outbox.id),
        "business_unit_public_id": business_unit,
        "campaign_public_id": str(event.payload_json.get("campaign_id")),
        "environment": body.environment,
        "synthetic": body.synthetic,
        "created_at": body.created_at.isoformat(),
        "completed_at": body.completed_at.isoformat(),
        "result": terminal_payload if body.terminal_status == "SUCCEEDED" else None,
        "bounded_error": body.bounded_error,
        "payload": terminal_payload,
    }
    db.add(OutboxEvent(
        integration_event_id=event.id,
        topic="integration.result",
        payload=odoo_payload,
        correlation_id=body.correlation_id,
    ))
    await _trace(db, body.correlation_id, "MIDDLEWARE_RESULT", body.execution_id, body.terminal_status)
    await db.commit()
    return {"accepted": True, "duplicate": False, "execution_id": body.execution_id, "status": body.terminal_status}


@router.get("/api/v1/integration/traces/{correlation_id}")
async def trace(correlation_id: str, db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(IntegrationTrace).where(IntegrationTrace.correlation_id == correlation_id).order_by(IntegrationTrace.created_at))).scalars().all()
    if not rows:
        raise HTTPException(404, "trace not found")
    return {"correlation_id": correlation_id, "stages": [{"stage": row.stage, "identity": row.identity, "status": row.status, "details": row.details, "created_at": row.created_at} for row in rows], "reconciled": {"WEBHOOK_RECEIVED", "N8N_EXECUTION_REGISTERED", "N8N_ACKNOWLEDGED", "MIDDLEWARE_RESULT"}.issubset({row.stage for row in rows})}
