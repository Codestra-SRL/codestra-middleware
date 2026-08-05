"""Middleware-owned, disabled-by-default Odoo-to-VICIdial assignment API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.vicidial_assignment import AssignmentPolicy, eligibility_errors, external_key
from app.db.models import AuditEvent, LeadIntelligenceRecord, LeadReview, VicidialAssignmentBatch, VicidialAssignmentItem
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/vicidial-assignments", tags=["vicidial-assignments"])


class EligibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    lead_record_id: UUID
    target_campaign_id: str = Field(min_length=1, max_length=128)
    target_list_id: str = Field(min_length=1, max_length=128)


class AssignmentBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str | None = Field(default=None, max_length=128)
    lead_record_ids: list[UUID] = Field(min_length=1, max_length=5)
    target_campaign_id: Literal["STAGING_CAMPAIGN"]
    target_list_id: Literal["STAGING_LEADS"]


def _assignment_role(role: str) -> None:
    if role not in {"VICIDIAL_ASSIGNMENT_REVIEWER", "VICIDIAL_ASSIGNMENT_MANAGER", "VICIDIAL_ASSIGNMENT_OPERATOR", "VICIDIAL_ASSIGNMENT_SERVICE"}:
        raise HTTPException(403, "VICIdial assignment role required")


async def _lead(db: AsyncSession, tenant: str, lead_id: UUID) -> LeadIntelligenceRecord:
    row = await db.scalar(select(LeadIntelligenceRecord).where(LeadIntelligenceRecord.id == lead_id, LeadIntelligenceRecord.tenant_id == tenant))
    if not row:
        raise HTTPException(404, "lead record not found")
    return row


def _lead_context(lead: LeadIntelligenceRecord, review: LeadReview | None) -> dict[str, Any]:
    return {
        "approved_for_import": bool(review and review.status == "APPROVED_FOR_IMPORT"),
        "odoo_lead_id": lead.odoo_lead_id,
        "external_key": external_key(lead.tenant_id, str(lead.id)) if lead.odoo_lead_id else None,
        "normalized_phone": lead.normalized_phone,
        "phone_confidence": 1.0 if lead.verification_status == "VERIFIED" else 0.0,
        "duplicate_status": lead.duplicate_status,
        "suppressed": lead.status in {"REJECTED", "SUPPRESSED"},
    }


@router.post("/eligibility/check")
async def check_eligibility(body: EligibilityRequest, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if body.tenant_id != tenant_header:
        raise HTTPException(403, "tenant scope mismatch")
    lead = await _lead(db, tenant_header, body.lead_record_id)
    review = await db.scalar(select(LeadReview).where(LeadReview.lead_record_id == lead.id, LeadReview.tenant_id == tenant_header))
    errors = eligibility_errors(_lead_context(lead, review), AssignmentPolicy(), target_campaign=body.target_campaign_id, target_list=body.target_list_id)
    return {"lead_record_id": str(lead.id), "status": "ELIGIBLE" if not errors else "INELIGIBLE", "errors": errors, "external_key": _lead_context(lead, review)["external_key"]}


@router.get("/eligibility/{lead_id}")
async def get_eligibility(lead_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    lead = await _lead(db, tenant_header, lead_id)
    review = await db.scalar(select(LeadReview).where(LeadReview.lead_record_id == lead.id, LeadReview.tenant_id == tenant_header))
    errors = eligibility_errors(_lead_context(lead, review), AssignmentPolicy(), target_campaign="STAGING_CAMPAIGN", target_list="STAGING_LEADS")
    return {"lead_record_id": str(lead.id), "status": "ELIGIBLE" if not errors else "INELIGIBLE", "errors": errors}


@router.post("/batches", status_code=202)
async def create_batch(body: AssignmentBatchCreate, tenant_header: str = Header(alias="X-Tenant-ID"), idempotency_key: str = Header(alias="Idempotency-Key"), role: str = Header(alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    _assignment_role(role)
    if tenant_header != body.tenant_id or not settings.vicidial_assignment_platform_enabled or not settings.vicidial_assignment_staging_enabled:
        raise HTTPException(409, "VICIdial staging assignment is disabled")
    if len(body.lead_record_ids) > settings.vicidial_assignment_max_batch_size:
        raise HTTPException(422, "assignment batch size exceeds staging limit")
    existing = await db.scalar(select(VicidialAssignmentBatch).where(VicidialAssignmentBatch.tenant_id == tenant_header, VicidialAssignmentBatch.idempotency_key == idempotency_key))
    if existing:
        return {"batch_id": str(existing.id), "batch_code": existing.batch_code, "status": existing.status, "duplicate": True}
    batch = VicidialAssignmentBatch(tenant_id=tenant_header, workspace_id=body.workspace_id, batch_code=f"STAGE-{uuid4().hex[:16]}", target_campaign_id=body.target_campaign_id, target_list_id=body.target_list_id, requested_by=role, idempotency_key=idempotency_key, correlation_id=str(uuid4()), lead_count=len(body.lead_record_ids))
    db.add(batch)
    await db.flush()
    for lead_id in body.lead_record_ids:
        lead = await _lead(db, tenant_header, lead_id)
        review = await db.scalar(select(LeadReview).where(LeadReview.lead_record_id == lead.id, LeadReview.tenant_id == tenant_header))
        errors = eligibility_errors(_lead_context(lead, review), AssignmentPolicy(), target_campaign=body.target_campaign_id, target_list=body.target_list_id)
        if errors:
            raise HTTPException(422, {"lead_record_id": str(lead_id), "eligibility_errors": errors})
        db.add(VicidialAssignmentItem(batch_id=batch.id, lead_record_id=lead.id, odoo_lead_id=lead.odoo_lead_id, vicidial_list_id=body.target_list_id, vicidial_campaign_id=body.target_campaign_id, external_key=external_key(tenant_header, str(lead.id))))
    db.add(AuditEvent(action="vicidial.assignment.batch.created", subject=str(batch.id), correlation_id=batch.correlation_id, decision="accepted", redacted_payload={"lead_count": batch.lead_count, "target_list_id": body.target_list_id}))
    await db.commit()
    return {"batch_id": str(batch.id), "batch_code": batch.batch_code, "status": batch.status, "lead_count": batch.lead_count, "duplicate": False}


@router.get("/batches")
async def list_batches(tenant_header: str = Header(alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    rows = (await db.scalars(select(VicidialAssignmentBatch).where(VicidialAssignmentBatch.tenant_id == tenant_header).order_by(VicidialAssignmentBatch.created_at.desc()).limit(100))).all()
    return {"items": [{"batch_id": str(row.id), "batch_code": row.batch_code, "status": row.status, "lead_count": row.lead_count, "success_count": row.success_count} for row in rows], "count": len(rows)}


@router.post("/batches/{batch_id}/approve")
async def approve_batch(batch_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if role != "VICIDIAL_ASSIGNMENT_MANAGER":
        raise HTTPException(403, "assignment manager approval required")
    batch = await db.scalar(select(VicidialAssignmentBatch).where(VicidialAssignmentBatch.id == batch_id, VicidialAssignmentBatch.tenant_id == tenant_header).with_for_update())
    if not batch or batch.status != "REQUESTED":
        raise HTTPException(409, "batch is not awaiting approval")
    batch.status = "APPROVED_FOR_ASSIGNMENT"
    batch.approved_by = role
    batch.approved_at = datetime.now(UTC)
    db.add(AuditEvent(action="vicidial.assignment.approved", subject=str(batch.id), correlation_id=batch.correlation_id, decision="accepted", redacted_payload={}))
    await db.commit()
    return {"batch_id": str(batch.id), "status": batch.status}


@router.post("/batches/{batch_id}/execute")
async def execute_batch(batch_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Assignment-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    _assignment_role(role)
    if not settings.vicidial_lead_create_enabled or not settings.vicidial_assignment_staging_enabled or not settings.vicidial_assignment_platform_enabled:
        raise HTTPException(409, "VICIdial lead creation is disabled")
    if settings.vicidial_live_dialing_enabled or settings.vicidial_campaign_activation_enabled:
        raise HTTPException(409, "live dialing and campaign activation must remain disabled")
    batch = await db.scalar(select(VicidialAssignmentBatch).where(VicidialAssignmentBatch.id == batch_id, VicidialAssignmentBatch.tenant_id == tenant_header).with_for_update())
    if not batch or batch.status != "APPROVED_FOR_ASSIGNMENT":
        raise HTTPException(409, "batch is not approved")
    batch.status = "ASSIGNMENT_QUEUED"
    await db.commit()
    return {"batch_id": str(batch.id), "status": batch.status, "execution": "queued"}


@router.post("/batches/{batch_id}/cancel")
async def cancel_batch(batch_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Assignment-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    _assignment_role(role)
    batch = await db.scalar(select(VicidialAssignmentBatch).where(VicidialAssignmentBatch.id == batch_id, VicidialAssignmentBatch.tenant_id == tenant_header).with_for_update())
    if not batch or batch.status in {"ASSIGNED", "CANCELLED"}:
        raise HTTPException(409, "batch cannot be cancelled")
    batch.status = "CANCELLED"
    batch.cancelled_at = datetime.now(UTC)
    await db.commit()
    return {"batch_id": str(batch.id), "status": batch.status}
