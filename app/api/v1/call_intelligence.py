"""Middleware-owned Call Intelligence control plane APIs."""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.call_intelligence import canonical_key, transition, validate_analysis, validate_transcript
from app.core.config import settings
from app.db.models import AuditEvent, CallAnalysis, CallIntelligenceJob, CallRecordingReference, CallTranscript
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/call-intelligence", tags=["call-intelligence"])


class CallCompletedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str | None = Field(default=None, max_length=128)
    vicidial_call_id: str = Field(min_length=1, max_length=128)
    vicidial_uniqueid: str = Field(min_length=1, max_length=128)
    odoo_lead_id: int | None = None
    campaign_id: str | None = None
    agent_user: str | None = None
    duration_seconds: int | None = Field(default=None, ge=0, le=86400)
    recording_id: str | None = Field(default=None, max_length=128)
    correlation_id: str | None = Field(default=None, max_length=128)


class TranscriptCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    provider: str = Field(min_length=1, max_length=64)
    payload: dict[str, Any]


class AnalysisCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    payload: dict[str, Any]
    model_code: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)


def _role(role: str, allowed: set[str]) -> None:
    if role not in allowed:
        raise HTTPException(403, "Call Intelligence permission required")


@router.post("/events/call-completed", status_code=202)
async def call_completed(body: CallCompletedEvent, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if body.tenant_id != tenant_header:
        raise HTTPException(403, "tenant scope mismatch")
    if not settings.call_intelligence_enabled:
        raise HTTPException(409, "Call Intelligence is disabled")
    key = canonical_key(body.tenant_id, body.vicidial_uniqueid)
    existing = await db.scalar(select(CallIntelligenceJob).where(CallIntelligenceJob.tenant_id == tenant_header, CallIntelligenceJob.idempotency_key == key))
    if existing:
        return {"job_id": str(existing.id), "status": existing.status, "duplicate": True}
    job = CallIntelligenceJob(tenant_id=tenant_header, workspace_id=body.workspace_id, vicidial_call_id=body.vicidial_call_id, vicidial_uniqueid=body.vicidial_uniqueid, odoo_lead_id=body.odoo_lead_id, campaign_id=body.campaign_id, agent_user=body.agent_user, duration_seconds=body.duration_seconds, idempotency_key=key, correlation_id=body.correlation_id or str(uuid4()))
    db.add(job)
    await db.flush()
    if body.recording_id:
        job.status = transition(job.status, "RECORDING_PENDING")
        job.status = transition(job.status, "RECORDING_AVAILABLE")
        db.add(CallRecordingReference(call_job_id=job.id, provider="vicidial", recording_id=body.recording_id, storage_reference=f"protected://vicidial/{body.recording_id}", format="unknown"))
    db.add(AuditEvent(action="call.intelligence.job.created", subject=str(job.id), correlation_id=job.correlation_id, decision="accepted", redacted_payload={"status": job.status}))
    await db.commit()
    return {"job_id": str(job.id), "status": job.status, "duplicate": False}


@router.get("/jobs")
async def list_jobs(tenant_header: str = Header(alias="X-Tenant-ID"), limit: int = 50, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    rows = (await db.scalars(select(CallIntelligenceJob).where(CallIntelligenceJob.tenant_id == tenant_header).order_by(CallIntelligenceJob.created_at.desc()).limit(min(limit, 100)))).all()
    return {"items": [{"job_id": str(row.id), "status": row.status, "uniqueid": row.vicidial_uniqueid, "created_at": row.created_at} for row in rows], "count": len(rows)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    row = await db.scalar(select(CallIntelligenceJob).where(CallIntelligenceJob.id == job_id, CallIntelligenceJob.tenant_id == tenant_header))
    if not row:
        raise HTTPException(404, "Call Intelligence job not found")
    return {"job_id": str(row.id), "status": row.status, "uniqueid": row.vicidial_uniqueid, "odoo_lead_id": row.odoo_lead_id, "recording_reference_id": str(row.recording_reference_id) if row.recording_reference_id else None}


@router.post("/jobs/{job_id}/transcript", status_code=202)
async def accept_transcript(body: TranscriptCallback, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    job = await db.scalar(select(CallIntelligenceJob).where(CallIntelligenceJob.id == body.job_id, CallIntelligenceJob.tenant_id == tenant_header).with_for_update())
    if not job:
        raise HTTPException(404, "Call Intelligence job not found")
    try:
        validate_transcript(body.payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = await db.scalar(select(CallTranscript).where(CallTranscript.call_job_id == job.id))
    if existing:
        return {"job_id": str(job.id), "transcript_id": str(existing.id), "duplicate": True}
    transcript_text = " ".join(segment["text"] for segment in body.payload["segments"])
    transcript = CallTranscript(call_job_id=job.id, model_code=body.payload["model_code"], model_version=body.payload["model_version"], language=body.payload["language"], language_confidence=body.payload["language_confidence"], speaker_count=body.payload.get("speaker_count", 0), transcript_text_encrypted_or_protected=transcript_text, segments=body.payload["segments"], redaction_status="REDACTED", duration_ms=body.payload.get("processing_duration_ms"))
    db.add(transcript)
    await db.flush()
    job.transcript_id = transcript.id
    job.status = transition(job.status, "TRANSCRIBED") if job.status == "TRANSCRIBING" else job.status
    db.add(AuditEvent(action="call.intelligence.transcript.accepted", subject=str(job.id), correlation_id=job.correlation_id, decision="accepted", redacted_payload={"redaction_status": "REDACTED"}))
    await db.commit()
    return {"job_id": str(job.id), "transcript_id": str(transcript.id), "duplicate": False}


@router.post("/jobs/{job_id}/analysis", status_code=202)
async def accept_analysis(body: AnalysisCallback, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    job = await db.scalar(select(CallIntelligenceJob).where(CallIntelligenceJob.id == body.job_id, CallIntelligenceJob.tenant_id == tenant_header).with_for_update())
    if not job:
        raise HTTPException(404, "Call Intelligence job not found")
    try:
        validate_analysis(body.payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = await db.scalar(select(CallAnalysis).where(CallAnalysis.call_job_id == job.id))
    if existing:
        return {"job_id": str(job.id), "analysis_id": str(existing.id), "duplicate": True}
    analysis = CallAnalysis(call_job_id=job.id, prompt_version=body.prompt_version, model_code=body.model_code, model_version=body.model_version, summary=body.payload["summary"], sentiment=body.payload["customer_sentiment"], disposition_recommendation=body.payload.get("disposition_recommendation"), objections=body.payload.get("objections", []), products_discussed=body.payload.get("products_discussed", []), commitments=body.payload.get("commitments", []), callback_recommendation=body.payload["callback"], next_best_action=body.payload.get("next_best_action"), compliance_findings=body.payload.get("compliance_findings", []), coaching_recommendations=body.payload.get("coaching_recommendations", []), confidence=body.payload["confidence"], raw_result_safe={"warning_count": len(body.payload.get("warnings", []))})
    db.add(analysis)
    await db.flush()
    job.analysis_id = analysis.id
    job.status = transition(job.status, "ANALYZED") if job.status == "ANALYZING" else job.status
    db.add(AuditEvent(action="call.intelligence.analysis.accepted", subject=str(job.id), correlation_id=job.correlation_id, decision="accepted", redacted_payload={"model_code": body.model_code, "prompt_version": body.prompt_version}))
    await db.commit()
    return {"job_id": str(job.id), "analysis_id": str(analysis.id), "duplicate": False}


@router.get("/jobs/{job_id}/transcript")
async def get_transcript(job_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    _role(role, {"CALL_INTELLIGENCE_VIEWER", "CALL_QA_REVIEWER", "CALL_QA_MANAGER", "CALL_COMPLIANCE_REVIEWER", "CALL_INTELLIGENCE_ADMIN", "AI_AUDITOR"})
    transcript = await db.scalar(select(CallTranscript).join(CallIntelligenceJob, CallIntelligenceJob.id == CallTranscript.call_job_id).where(CallTranscript.call_job_id == job_id, CallIntelligenceJob.tenant_id == tenant_header))
    if not transcript:
        raise HTTPException(404, "transcript not found")
    return {"transcript_id": str(transcript.id), "language": transcript.language, "segments": transcript.segments, "redaction_status": transcript.redaction_status}
