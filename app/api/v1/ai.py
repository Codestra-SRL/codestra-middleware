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
from app.core.ai_schema_registry import validate_result_schema
from app.adapters.ai_gateway import AIGatewayClient
from app.db.models import (
    AIApproval,
    AIJob,
    AIJobEvent,
    AuditEvent,
    LeadIntelligenceRecord,
    LeadSearch,
    OutboxEvent,
    PublisherNonce,
)
from app.db.session import get_session
from app.metrics import AI_JOB_STATUS, AI_JOBS, AI_RESULT_REPLAYS, AI_WORKFLOW_RESULTS, LEAD_SEARCHES

router = APIRouter(prefix="/api/v1/ai", tags=["ai-jobs"])
lead_intelligence_router = APIRouter(prefix="/api/v1/lead-intelligence", tags=["lead-intelligence"])
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
    result_schema: str | None = Field(default=None, max_length=96)
    result_schema_version: int | None = Field(default=None, ge=1)
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
    AI_JOBS.labels(body.service_code, body.task_code).inc()
    AI_JOB_STATUS.labels("QUEUED" if not body.requires_approval else "APPROVAL_REQUIRED").inc()
    await db.commit()
    return _serialize(job)


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    job = await db.scalar(select(AIJob).where(AIJob.id == job_id, AIJob.tenant_id == tenant_header))
    if not job:
        raise HTTPException(404, "AI job not found")
    return _serialize(job)


@router.get("/gateway/health")
async def ai_gateway_health() -> dict[str, Any]:
    client = AIGatewayClient(
        settings.ai_gateway_base_url,
        settings.ai_gateway_api_key_file,
        timeout_seconds=settings.ai_gateway_timeout_seconds,
        model_code=settings.ai_gateway_model_code,
        health_path=settings.ai_gateway_health_path,
    )
    try:
        result = await client.health()
    finally:
        await client.aclose()
    return {
        "component": settings.ai_gateway_model_code,
        "model_status": settings.ai_gateway_model_status,
        **result,
    }


@router.get("/jobs")
async def list_jobs(
    tenant_header: str = Header(alias="X-Tenant-ID"),
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not 1 <= limit <= 100:
        raise HTTPException(422, "limit must be between 1 and 100")
    query = select(AIJob).where(AIJob.tenant_id == tenant_header).order_by(AIJob.created_at.desc()).limit(limit)
    if status:
        query = query.where(AIJob.status == status)
    rows = (await db.scalars(query)).all()
    return {"items": [_serialize(job) for job in rows], "count": len(rows)}


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


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    job = await db.scalar(select(AIJob).where(AIJob.id == job_id, AIJob.tenant_id == tenant_header).with_for_update())
    if not job:
        raise HTTPException(404, "AI job not found")
    if job.status not in {"FAILED", "UNKNOWN"}:
        raise HTTPException(409, "AI job is not retryable")
    job.status = "RETRY_SCHEDULED"
    event = {"message_id": str(uuid4()), "event_id": str(uuid4()), "event_type": "ai.job.retry_scheduled", "event_version": 1, "tenant_id": job.tenant_id, "workspace_id": job.workspace_id, "job_id": str(job.id), "correlation_id": job.correlation_id, "causation_id": str(job.id), "occurred_at": datetime.now(UTC).isoformat(), "producer": "codestra-middleware", "payload": {"attempt_count": job.attempt_count}}
    db.add(AIJobEvent(ai_job_id=job.id, event_type="ai.job.retry_scheduled", payload=event))
    db.add(OutboxEvent(topic="ai.job.retry_scheduled", payload=event, correlation_id=job.correlation_id))
    db.add(AuditEvent(action="ai.job.retried", subject=str(job.id), correlation_id=job.correlation_id, decision="accepted", redacted_payload={}))
    await db.commit()
    return _serialize(job)


def _approval_role(role: str) -> None:
    if role not in {"AI_PLATFORM_ADMIN", "AI_SECURITY_ADMIN", "AI_MODEL_MANAGER", "LEAD_REVIEWER"}:
        raise HTTPException(403, "AI approval role required")


@router.get("/approvals")
async def list_approvals(tenant_header: str = Header(alias="X-Tenant-ID"), limit: int = 50, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not 1 <= limit <= 100:
        raise HTTPException(422, "limit must be between 1 and 100")
    rows = (await db.scalars(select(AIApproval).where(AIApproval.tenant_id == tenant_header).order_by(AIApproval.created_at.desc()).limit(limit))).all()
    return {"items": [{"approval_id": str(row.id), "job_id": str(row.ai_job_id) if row.ai_job_id else None, "action_type": row.action_type, "status": row.status} for row in rows], "count": len(rows)}


@router.get("/approvals/{approval_id}")
async def get_approval(approval_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    row = await db.scalar(select(AIApproval).where(AIApproval.id == approval_id, AIApproval.tenant_id == tenant_header))
    if not row:
        raise HTTPException(404, "AI approval not found")
    return {"approval_id": str(row.id), "job_id": str(row.ai_job_id) if row.ai_job_id else None, "action_type": row.action_type, "status": row.status, "action_payload": row.action_payload}


async def _review_approval(approval_id: UUID, tenant_header: str, role: str, approved: bool, comment: str | None, db: AsyncSession) -> dict[str, Any]:
    _approval_role(role)
    row = await db.scalar(select(AIApproval).where(AIApproval.id == approval_id, AIApproval.tenant_id == tenant_header).with_for_update())
    if not row:
        raise HTTPException(404, "AI approval not found")
    if row.status != "PENDING":
        raise HTTPException(409, "AI approval is not pending")
    row.status = "APPROVED" if approved else "REJECTED"
    row.reviewed_by = role
    row.review_comment = comment
    row.reviewed_at = datetime.now(UTC)
    if row.ai_job_id:
        job = await db.scalar(select(AIJob).where(AIJob.id == row.ai_job_id).with_for_update())
        if job and job.status == "APPROVAL_REQUIRED":
            job.status = "QUEUED" if approved else "REJECTED"
            action = "ai.job.approved" if approved else "ai.job.rejected"
            db.add(AuditEvent(action=action, subject=str(job.id), correlation_id=job.correlation_id, decision=row.status.lower(), redacted_payload={"approval_id": str(row.id)}))
    await db.commit()
    return {"approval_id": str(row.id), "status": row.status}


@router.post("/approvals/{approval_id}/approve")
async def approve_approval(approval_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await _review_approval(approval_id, tenant_header, role, True, None, db)


@router.post("/approvals/{approval_id}/reject")
async def reject_approval(approval_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), comment: str | None = None, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not comment:
        raise HTTPException(422, "rejection comment required")
    return await _review_approval(approval_id, tenant_header, role, False, comment, db)


class LeadSearchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str | None = Field(default=None, max_length=128)
    industry: str | None = Field(default=None, max_length=128)
    keywords: list[str] = Field(default_factory=list, max_length=32)
    location: dict[str, Any] = Field(default_factory=dict)
    requirements: dict[str, bool] = Field(default_factory=dict)
    maximum_results: int = Field(default=100, ge=1, le=10000)
    minimum_confidence: float = Field(default=0.75, ge=0, le=1)
    target_odoo_team: str | None = Field(default=None, max_length=128)


class LeadReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lead_ids: list[UUID] = Field(min_length=1, max_length=100)
    comment: str | None = Field(default=None, max_length=512)


@router.post("/lead-intelligence/searches", status_code=202)
async def create_lead_search(body: LeadSearchCreate, tenant_header: str = Header(alias="X-Tenant-ID"), idempotency_key: str = Header(alias="Idempotency-Key"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if tenant_header != body.tenant_id:
        raise HTTPException(403, "tenant scope mismatch")
    ai_request = AIJobCreate(tenant_id=body.tenant_id, workspace_id=body.workspace_id, service_code="lead_intelligence", task_code="lead_search", input_payload={"industry": body.industry, "keywords": body.keywords}, context_payload={"location": body.location, "requirements": body.requirements, "maximum_results": body.maximum_results, "minimum_confidence": body.minimum_confidence, "target_odoo_team": body.target_odoo_team}, idempotency_key=idempotency_key, requires_approval=True, environment="test")
    digest = _request_hash(ai_request)
    existing = await db.scalar(select(AIJob).where(AIJob.tenant_id == body.tenant_id, AIJob.idempotency_key == idempotency_key))
    if existing:
        if existing.request_hash != digest:
            raise HTTPException(409, "idempotency key conflict")
        search = await db.scalar(select(LeadSearch).where(LeadSearch.ai_job_id == existing.id))
        return {"search_id": str(search.id) if search else None, "job_id": str(existing.id), "duplicate": True}
    job = AIJob(tenant_id=body.tenant_id, workspace_id=body.workspace_id, service_code="lead_intelligence", task_code="lead_search", status="APPROVAL_REQUIRED", priority=5, input_payload=ai_request.input_payload, context_payload=ai_request.context_payload, idempotency_key=idempotency_key, request_hash=digest, correlation_id=ai_request.correlation_id, requires_approval=True)
    db.add(job)
    await db.flush()
    search = LeadSearch(tenant_id=body.tenant_id, workspace_id=body.workspace_id, ai_job_id=job.id, industry=body.industry, keywords=body.keywords, location_payload=body.location, requirements_payload=body.requirements, maximum_results=body.maximum_results, minimum_confidence=body.minimum_confidence, target_odoo_team=body.target_odoo_team)
    db.add(search)
    await db.flush()
    db.add(AIApproval(tenant_id=body.tenant_id, workspace_id=body.workspace_id, ai_job_id=job.id, action_type="LEAD_SEARCH", action_payload={"search_id": str(search.id) if search.id else None}, status="PENDING"))
    db.add(AuditEvent(action="lead.search.created", subject=str(search.id), correlation_id=job.correlation_id, decision="accepted", redacted_payload={"job_id": str(job.id)}))
    AI_JOBS.labels("lead_intelligence", "lead_search").inc()
    LEAD_SEARCHES.inc()
    AI_JOB_STATUS.labels("APPROVAL_REQUIRED").inc()
    await db.commit()
    return {"search_id": str(search.id), "job_id": str(job.id), "status": job.status, "duplicate": False}


@router.get("/lead-intelligence/searches")
async def list_lead_searches(tenant_header: str = Header(alias="X-Tenant-ID"), limit: int = 50, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not 1 <= limit <= 100:
        raise HTTPException(422, "limit must be between 1 and 100")
    rows = (await db.scalars(select(LeadSearch).where(LeadSearch.tenant_id == tenant_header).order_by(LeadSearch.created_at.desc()).limit(limit))).all()
    return {"items": [{"search_id": str(row.id), "job_id": str(row.ai_job_id), "status": row.status, "industry": row.industry} for row in rows], "count": len(rows)}


@router.get("/lead-intelligence/searches/{search_id}")
async def get_lead_search(search_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    row = await db.scalar(select(LeadSearch).where(LeadSearch.id == search_id, LeadSearch.tenant_id == tenant_header))
    if not row:
        raise HTTPException(404, "lead search not found")
    return {"search_id": str(row.id), "job_id": str(row.ai_job_id), "status": row.status, "industry": row.industry, "keywords": row.keywords, "location": row.location_payload, "requirements": row.requirements_payload}


@router.post("/lead-intelligence/leads/import")
async def import_leads(tenant_header: str = Header(alias="X-Tenant-ID")) -> dict[str, Any]:
    if not (
        settings.lead_import_enabled
        and settings.odoo_ai_writes_enabled
        and settings.odoo_lead_apply_enabled
    ):
        raise HTTPException(409, "lead import is disabled")
    return {"status": "not_implemented", "tenant_id": tenant_header}


@lead_intelligence_router.get("/searches/{search_id}/leads")
async def list_search_leads(
    search_id: UUID,
    tenant_header: str = Header(alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    search = await db.scalar(select(LeadSearch).where(LeadSearch.id == search_id, LeadSearch.tenant_id == tenant_header))
    if not search:
        raise HTTPException(404, "lead search not found")
    rows = (await db.scalars(select(LeadIntelligenceRecord).where(LeadIntelligenceRecord.search_id == search_id, LeadIntelligenceRecord.tenant_id == tenant_header).order_by(LeadIntelligenceRecord.created_at))).all()
    return {"items": [{"lead_id": str(row.id), "company_name": row.company_name, "website": row.website, "verification_status": row.verification_status, "duplicate_status": row.duplicate_status, "lead_score": row.lead_score, "status": row.status} for row in rows], "count": len(rows)}


@lead_intelligence_router.get("/leads/{lead_id}")
async def get_intelligence_lead(
    lead_id: UUID,
    tenant_header: str = Header(alias="X-Tenant-ID"),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await db.scalar(select(LeadIntelligenceRecord).where(LeadIntelligenceRecord.id == lead_id, LeadIntelligenceRecord.tenant_id == tenant_header))
    if not row:
        raise HTTPException(404, "lead not found")
    return {"lead_id": str(row.id), "company_name": row.company_name, "website": row.website, "phone": row.phone, "email": row.email, "ownership_status": row.ownership_status, "ownership_confidence": row.ownership_confidence, "verification_status": row.verification_status, "lead_score": row.lead_score, "duplicate_status": row.duplicate_status, "status": row.status}


async def _review_leads(body: LeadReview, tenant_header: str, role: str, approved: bool, db: AsyncSession) -> dict[str, Any]:
    _approval_role(role)
    rows = (await db.scalars(select(LeadIntelligenceRecord).where(LeadIntelligenceRecord.id.in_(body.lead_ids), LeadIntelligenceRecord.tenant_id == tenant_header).with_for_update())).all()
    if len(rows) != len(set(body.lead_ids)):
        raise HTTPException(404, "one or more leads not found")
    status = "APPROVED" if approved else "REJECTED"
    for row in rows:
        row.status = status
        db.add(AuditEvent(action="lead.review.approved" if approved else "lead.review.rejected", subject=str(row.id), correlation_id=str(row.id), decision=status.lower(), redacted_payload={"comment": body.comment} if body.comment else {}))
    await db.commit()
    return {"status": status, "lead_ids": [str(row.id) for row in rows]}


@lead_intelligence_router.post("/leads/approve")
async def approve_leads(body: LeadReview, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await _review_leads(body, tenant_header, role, True, db)


@lead_intelligence_router.post("/leads/reject")
async def reject_leads(body: LeadReview, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    return await _review_leads(body, tenant_header, role, False, db)


@lead_intelligence_router.post("/leads/import")
async def import_lead_selection(tenant_header: str = Header(alias="X-Tenant-ID")) -> dict[str, Any]:
    if not (settings.lead_import_enabled and settings.odoo_ai_writes_enabled and settings.odoo_lead_apply_enabled):
        raise HTTPException(409, "lead import is disabled")
    return {"status": "not_implemented", "tenant_id": tenant_header}


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
    try:
        validate_result_schema(body.result_schema, body.output_payload)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(422, "unregistered or invalid AI output schema") from exc
    job = await db.scalar(select(AIJob).where(AIJob.id == job_id, AIJob.tenant_id == tenant_header).with_for_update())
    if not job:
        raise HTTPException(404, "AI job not found")
    if job.status == "COMPLETED":
        AI_RESULT_REPLAYS.inc()
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
    AI_WORKFLOW_RESULTS.labels(body.status).inc()
    AI_JOB_STATUS.labels(job.status).inc()
    await db.commit()
    return _serialize(job)
