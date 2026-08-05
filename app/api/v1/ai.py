"""Middleware-owned AI job lifecycle; provider execution is asynchronous."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from time import time
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import AIJob, AIJobEvent, AuditEvent, OutboxEvent, PublisherNonce
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/ai", tags=["ai-jobs"])
ALLOWED_ENVIRONMENTS = {"test", "staging", "integration", "preproduction"}
SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "refresh_token",
    "private_key",
}
TERMINAL = {"COMPLETED", "FAILED", "REJECTED", "CANCELLED"}


class AIJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str | None = Field(default=None, max_length=128)
    service_code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_.-]+$")
    task_code: str = Field(min_length=1, max_length=96, pattern=r"^[a-z][a-z0-9_.-]+$")
    priority: int = Field(default=5, ge=0, le=9)
    requested_by: str | None = Field(default=None, max_length=128)
    prompt_version_id: str | None = Field(default=None, max_length=128)
    model_policy_id: str | None = Field(default=None, max_length=128)
    input_payload: dict[str, Any]
    context_payload: dict[str, Any] | None = None
    idempotency_key: str = Field(min_length=16, max_length=255)
    correlation_id: str = Field(default_factory=lambda: str(uuid4()), max_length=128)
    requires_approval: bool = False
    environment: Literal["test", "staging", "integration", "preproduction"] = "test"


class AIJobResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["completed", "failed", "unknown"]
    output_payload: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, max_length=512)
    workflow_execution_id: str = Field(min_length=1, max_length=128)
    model_id: str | None = Field(default=None, max_length=128)


def _contains_sensitive(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key.lower() in SENSITIVE_KEYS or _contains_sensitive(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive(item) for item in value)
    return False


def _request_hash(body: AIJobCreate) -> str:
    payload = body.model_dump(mode="json")
    # Correlation and idempotency values identify the request; they are not
    # business input and must not make a replay look like a different job.
    payload.pop("correlation_id", None)
    payload.pop("idempotency_key", None)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _serialize(job: AIJob, *, duplicate: bool = False) -> dict[str, Any]:
    return {
        "job_id": str(job.id),
        "tenant_id": job.tenant_id,
        "workspace_id": job.workspace_id,
        "service_code": job.service_code,
        "task_code": job.task_code,
        "status": job.status,
        "priority": job.priority,
        "correlation_id": job.correlation_id,
        "idempotency_key": job.idempotency_key,
        "requires_approval": job.requires_approval,
        "attempt_count": job.attempt_count,
        "duplicate": duplicate,
    }


@router.post("/jobs", status_code=202)
async def create_job(
    body: AIJobCreate,
    tenant_header: str = Header(alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if tenant_header != body.tenant_id:
        raise HTTPException(403, "tenant scope mismatch")
    if body.environment not in ALLOWED_ENVIRONMENTS:
        raise HTTPException(403, "environment is not permitted")
    if _contains_sensitive(body.input_payload) or _contains_sensitive(body.context_payload):
        raise HTTPException(422, "sensitive input fields are prohibited")
    digest = _request_hash(body)
    existing = await db.scalar(
        select(AIJob).where(
            AIJob.tenant_id == body.tenant_id,
            AIJob.idempotency_key == body.idempotency_key,
        )
    )
    if existing:
        if existing.request_hash != digest:
            raise HTTPException(409, "idempotency key conflict")
        return _serialize(existing, duplicate=True)
    job = AIJob(
        tenant_id=body.tenant_id,
        workspace_id=body.workspace_id,
        service_code=body.service_code,
        task_code=body.task_code,
        status="APPROVAL_REQUIRED" if body.requires_approval else "QUEUED",
        priority=body.priority,
        requested_by=body.requested_by,
        prompt_version_id=body.prompt_version_id,
        model_policy_id=body.model_policy_id,
        input_payload=body.input_payload,
        context_payload=body.context_payload,
        idempotency_key=body.idempotency_key,
        request_hash=digest,
        correlation_id=body.correlation_id,
        requires_approval=body.requires_approval,
    )
    db.add(job)
    await db.flush()
    event = {
        "message_id": str(uuid4()),
        "event_id": str(uuid4()),
        "event_type": "ai.job.requested",
        "event_version": 1,
        "tenant_id": body.tenant_id,
        "workspace_id": body.workspace_id,
        "job_id": str(job.id),
        "correlation_id": body.correlation_id,
        "causation_id": body.idempotency_key,
        "occurred_at": datetime.now(UTC).isoformat(),
        "producer": "codestra-middleware",
        "payload": {
            "service_code": body.service_code,
            "task_code": body.task_code,
            "priority": body.priority,
            "input_payload": body.input_payload,
            "context_payload": body.context_payload,
            "prompt_version_id": body.prompt_version_id,
            "model_policy_id": body.model_policy_id,
            "requires_approval": body.requires_approval,
        },
    }
    db.add(AIJobEvent(ai_job_id=job.id, event_type="ai.job.requested", payload=event))
    db.add(OutboxEvent(topic="ai.job.requested", payload=event, correlation_id=body.correlation_id))
    db.add(
        AuditEvent(
            action="ai.job.created",
            subject=str(job.id),
            correlation_id=body.correlation_id,
            decision="accepted",
            redacted_payload={"service_code": body.service_code, "task_code": body.task_code},
        )
    )
    await db.commit()
    return _serialize(job)


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    job = await db.scalar(select(AIJob).where(AIJob.id == job_id, AIJob.tenant_id == tenant_header))
    if not job:
        raise HTTPException(404, "AI job not found")
    return _serialize(job)


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    job = await db.scalar(select(AIJob).where(AIJob.id == job_id, AIJob.tenant_id == tenant_header).with_for_update())
    if not job:
        raise HTTPException(404, "AI job not found")
    if job.status in TERMINAL:
        raise HTTPException(409, "AI job is terminal")
    job.status = "CANCELLED"
    job.completed_at = datetime.now(UTC)
    db.add(AuditEvent(action="ai.job.cancelled", subject=str(job.id), correlation_id=job.correlation_id, decision="accepted", redacted_payload={}))
    await db.commit()
    return _serialize(job)


@router.post("/jobs/{job_id}/result", status_code=202)
async def result_job(
    job_id: UUID,
    request: Request,
    tenant_header: str = Header(alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    raw = await request.body()
    timestamp = request.headers.get("X-Codestra-Timestamp", "")
    nonce = request.headers.get("X-Codestra-Nonce", "")
    signature = request.headers.get("X-Codestra-Signature", "")
    service = request.headers.get("X-Codestra-Service", "")
    try:
        signed_at = int(timestamp)
    except ValueError as exc:
        raise HTTPException(401, "invalid callback timestamp") from exc
    if (
        service != "n8n-ai-result-writer"
        or not nonce
        or abs(time() - signed_at) > 300
        or not settings.lead_automation_hmac_secret
    ):
        raise HTTPException(401, "callback authentication failed")
    expected = hmac.new(
        settings.lead_automation_hmac_secret.encode(),
        f"{timestamp}.".encode() + raw,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "callback authentication failed")
    if await db.scalar(
        select(PublisherNonce).where(
            PublisherNonce.key_id == service, PublisherNonce.nonce == nonce
        )
    ):
        raise HTTPException(409, "callback replay rejected")
    db.add(
        PublisherNonce(
            key_id=service,
            nonce=nonce,
            signed_at=signed_at,
            expires_at=datetime.now(UTC) + timedelta(seconds=300),
        )
    )
    try:
        body = AIJobResult.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        await db.rollback()
        raise HTTPException(422, "invalid AI result schema") from exc
    job = await db.scalar(select(AIJob).where(AIJob.id == job_id, AIJob.tenant_id == tenant_header).with_for_update())
    if not job:
        raise HTTPException(404, "AI job not found")
    if job.status == "COMPLETED":
        return _serialize(job, duplicate=True)
    if job.status in {"CANCELLED", "REJECTED"}:
        raise HTTPException(409, "AI job cannot accept a result")
    job.attempt_count += 1
    job.output_payload = body.output_payload
    job.error_code = body.error_code
    job.error_message = body.error_message
    job.status = "COMPLETED" if body.status == "completed" else "UNKNOWN" if body.status == "unknown" else "FAILED"
    job.completed_at = datetime.now(UTC)
    db.add(AuditEvent(action="ai.job.result_received", subject=str(job.id), correlation_id=job.correlation_id, decision=job.status.lower(), redacted_payload={"workflow_execution_id": body.workflow_execution_id, "model_id": body.model_id}))
    await db.commit()
    return _serialize(job)
