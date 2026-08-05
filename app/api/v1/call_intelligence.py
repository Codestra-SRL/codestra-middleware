from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.call_intelligence.domain import (
    CallJob,
    IdempotencyStore,
    JobStatus,
    ProcessingPolicy,
)

router = APIRouter(prefix="/api/v1/call-intelligence", tags=["call-intelligence"])
store = IdempotencyStore()
jobs: dict[UUID, CallJob] = {}


class CompletedCall(BaseModel):
    tenant_id: UUID
    vicidial_uniqueid: str = Field(min_length=1, max_length=128)
    vicidial_call_id: str = Field(min_length=1, max_length=128)
    campaign_id: str = Field(min_length=1, max_length=64)
    agent_user: str = Field(min_length=1, max_length=64)
    processing_policy: ProcessingPolicy = ProcessingPolicy.DISABLED


def get_job(job_id: UUID) -> CallJob:
    if job_id not in jobs:
        raise HTTPException(404, "call intelligence job not found")
    return jobs[job_id]


@router.post("/events/call-completed", status_code=202)
def call_completed(
    event: CompletedCall, idempotency_key: str = Header(..., alias="Idempotency-Key")
) -> dict:
    candidate = CallJob(**event.model_dump(exclude={"processing_policy"}))
    job, created = store.create_job(candidate)
    jobs[job.id] = job
    if created:
        job.transition(JobStatus.RECORDING_PENDING, "vicidial-event")
        if event.processing_policy == ProcessingPolicy.DISABLED:
            job.transition(JobStatus.POLICY_BLOCKED, "policy-gate")
    return {
        "job_id": str(job.id),
        "status": job.status,
        "created": created,
        "external_key": job.external_key,
    }


@router.get("/jobs")
def list_jobs() -> list[dict]:
    return [
        {"id": str(j.id), "status": j.status, "external_key": j.external_key}
        for j in jobs.values()
    ]


@router.get("/jobs/{job_id}")
def job_detail(job_id: UUID) -> dict:
    job = get_job(job_id)
    return {
        "id": str(job.id),
        "status": job.status,
        "external_key": job.external_key,
        "audit": job.audit,
    }


@router.post("/jobs/{job_id}/retry")
def retry_job(
    job_id: UUID, idempotency_key: str = Header(..., alias="Idempotency-Key")
) -> dict:
    job = get_job(job_id)
    if job.status not in {
        JobStatus.FAILED,
        JobStatus.UNKNOWN,
        JobStatus.RETRY_SCHEDULED,
    }:
        raise HTTPException(409, "job is not retryable")
    if job.status != JobStatus.RETRY_SCHEDULED:
        old = job.status
        job.status = JobStatus.RETRY_SCHEDULED
        job.audit.append(
            __import__(
                "app.call_intelligence.domain", fromlist=["AuditEvent"]
            ).AuditEvent(old, JobStatus.RETRY_SCHEDULED, "operator")
        )
    return {"job_id": str(job.id), "status": job.status}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: UUID, idempotency_key: str = Header(..., alias="Idempotency-Key")
) -> dict:
    job = get_job(job_id)
    job.transition(JobStatus.CANCELLED, "operator")
    return {"job_id": str(job.id), "status": job.status}


@router.post("/jobs/{job_id}/reconcile")
def reconcile_job(
    job_id: UUID, idempotency_key: str = Header(..., alias="Idempotency-Key")
) -> dict:
    job = get_job(job_id)
    return {"job_id": str(job.id), "status": job.status, "reconciliation": "QUEUED"}


@router.get("/jobs/{job_id}/transcript")
def transcript(job_id: UUID, request: Request) -> dict:
    get_job(job_id)
    if "CALL_TRANSCRIPT_VIEW" not in request.headers.get(
        "X-Codestra-Permissions", ""
    ).split(","):
        raise HTTPException(403, "transcript permission required")
    return {
        "job_id": str(job_id),
        "redaction_status": "REDACTED",
        "segments": [],
        "access_audited": True,
    }


@router.get("/qa")
def qa_list() -> list:
    return []


@router.get("/qa/{qa_id}")
def qa_detail(qa_id: UUID) -> dict:
    return {"id": str(qa_id), "review_status": "PENDING"}


@router.post("/qa/{qa_id}/{action}")
def qa_mutation(
    qa_id: UUID,
    action: Literal["start-review", "confirm", "override", "escalate"],
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    return {"id": str(qa_id), "action": action, "human_review": True}


@router.get("/compliance-alerts")
def alert_list() -> list:
    return []


@router.get("/compliance-alerts/{alert_id}")
def alert_detail(alert_id: UUID) -> dict:
    return {"id": str(alert_id), "status": "OPEN"}


@router.post("/compliance-alerts/{alert_id}/{action}")
def alert_mutation(
    alert_id: UUID,
    action: Literal["assign", "resolve"],
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> dict:
    return {"id": str(alert_id), "action": action, "actor_required": True}
