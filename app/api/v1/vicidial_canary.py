"""Fail-closed governance API for a one-lead, one-call VICIdial canary.

This module only records and gates an explicitly authorized canary. It never
performs a dial itself; a separately reviewed adapter must consume an approved
run, and all live-call flags remain disabled by default.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.vicidial_canary import CanaryAuthorization, enforce_limits, enforce_window, validate_authorization, phone_hash
from app.db.models import AuditEvent, VicidialCampaignActivationApproval, VicidialCanaryEvent, VicidialCanaryRun
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/vicidial-canary", tags=["vicidial-canary"])


class ActivationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str | None = Field(default=None, max_length=128)
    campaign_id: Literal["STAGING_CAMPAIGN"]
    list_id: Literal["STAGING_LEADS"]
    maintenance_window_start: datetime
    maintenance_window_end: datetime
    authorization_reference: str = Field(min_length=8, max_length=255)
    reason: str = Field(min_length=8, max_length=1024)


class CanaryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assignment_item_id: UUID
    test_phone: str = Field(min_length=8, max_length=32)
    agent_reference: str = Field(min_length=1, max_length=128)
    carrier_check: Literal["PASSED"]
    dialing_window_check: Literal["PASSED"]


def _role(role: str, allowed: set[str]) -> None:
    if role not in allowed:
        raise HTTPException(403, "VICIdial canary role required")


@router.post("/activations", status_code=202)
async def request_activation(body: ActivationRequest, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), idempotency_key: str = Header(alias="Idempotency-Key"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    _role(role, {"VICIDIAL_CANARY_MANAGER", "VICIDIAL_ASSIGNMENT_MANAGER"})
    if body.tenant_id != tenant_header:
        raise HTTPException(403, "tenant scope mismatch")
    if not settings.vicidial_assignment_platform_enabled or not settings.vicidial_assignment_staging_enabled:
        raise HTTPException(409, "VICIdial staging platform is disabled")
    if body.maintenance_window_end <= body.maintenance_window_start:
        raise HTTPException(422, "maintenance window is invalid")
    existing = await db.scalar(select(VicidialCampaignActivationApproval).where(VicidialCampaignActivationApproval.tenant_id == tenant_header, VicidialCampaignActivationApproval.authorization_reference == body.authorization_reference))
    if existing:
        return {"approval_id": str(existing.id), "status": existing.status, "duplicate": True}
    row = VicidialCampaignActivationApproval(tenant_id=tenant_header, workspace_id=body.workspace_id, campaign_id=body.campaign_id, list_id=body.list_id, requested_by=role, authorization_reference=body.authorization_reference, maintenance_window_start=body.maintenance_window_start, maintenance_window_end=body.maintenance_window_end, reason=body.reason)
    db.add(row)
    await db.flush()
    db.add(AuditEvent(action="vicidial.canary.activation.requested", subject=str(row.id), correlation_id=str(uuid4()), decision="accepted", redacted_payload={"campaign_id": body.campaign_id, "list_id": body.list_id}))
    await db.commit()
    return {"approval_id": str(row.id), "status": row.status, "duplicate": False}


@router.post("/activations/{approval_id}/approve")
async def approve_activation(approval_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    _role(role, {"VICIDIAL_CANARY_APPROVER"})
    row = await db.scalar(select(VicidialCampaignActivationApproval).where(VicidialCampaignActivationApproval.id == approval_id, VicidialCampaignActivationApproval.tenant_id == tenant_header).with_for_update())
    if not row or row.status != "REQUESTED":
        raise HTTPException(409, "activation is not awaiting approval")
    auth = CanaryAuthorization(row.campaign_id, row.list_id, row.maintenance_window_start, row.maintenance_window_end, row.authorization_reference or "", role)
    try:
        validate_authorization(auth)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row.status = "APPROVED"
    row.approved_by = role
    row.approved_at = datetime.now(UTC)
    db.add(AuditEvent(action="vicidial.canary.activation.approved", subject=str(row.id), correlation_id=str(uuid4()), decision="accepted", redacted_payload={"max_calls": 1, "max_leads": 1}))
    await db.commit()
    return {"approval_id": str(row.id), "status": row.status, "max_calls": 1, "max_leads": 1}


@router.post("/activations/{approval_id}/activate")
async def activate(approval_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    _role(role, {"VICIDIAL_CANARY_MANAGER", "VICIDIAL_CANARY_OPERATOR"})
    if not settings.vicidial_campaign_activation_enabled or not settings.vicidial_canary_enabled or not settings.vicidial_live_canary_authorized:
        raise HTTPException(409, "live canary activation is disabled or unauthorized")
    row = await db.scalar(select(VicidialCampaignActivationApproval).where(VicidialCampaignActivationApproval.id == approval_id, VicidialCampaignActivationApproval.tenant_id == tenant_header).with_for_update())
    if not row or row.status != "APPROVED":
        raise HTTPException(409, "activation is not approved")
    enforce_window(datetime.now(UTC), start=row.maintenance_window_start, end=row.maintenance_window_end)
    row.status = "ACTIVATED"
    row.activated_at = datetime.now(UTC)
    await db.commit()
    return {"approval_id": str(row.id), "status": row.status}


@router.post("/activations/{approval_id}/shutdown")
async def shutdown(approval_id: UUID, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    _role(role, {"VICIDIAL_CANARY_MANAGER", "VICIDIAL_CANARY_OPERATOR", "VICIDIAL_CANARY_APPROVER"})
    row = await db.scalar(select(VicidialCampaignActivationApproval).where(VicidialCampaignActivationApproval.id == approval_id, VicidialCampaignActivationApproval.tenant_id == tenant_header).with_for_update())
    if not row:
        raise HTTPException(404, "activation not found")
    row.status = "SHUT_DOWN"
    row.shut_down_at = datetime.now(UTC)
    await db.commit()
    return {"approval_id": str(row.id), "status": row.status}


@router.post("/activations/{approval_id}/runs", status_code=202)
async def authorize_run(approval_id: UUID, body: CanaryRunRequest, tenant_header: str = Header(alias="X-Tenant-ID"), role: str = Header(alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    _role(role, {"VICIDIAL_CANARY_OPERATOR", "VICIDIAL_CANARY_MANAGER"})
    if not settings.vicidial_live_canary_authorized:
        raise HTTPException(409, "live canary authorization is disabled")
    approval = await db.scalar(select(VicidialCampaignActivationApproval).where(VicidialCampaignActivationApproval.id == approval_id, VicidialCampaignActivationApproval.tenant_id == tenant_header))
    if not approval or approval.status != "ACTIVATED":
        raise HTTPException(409, "campaign is not activated")
    existing = await db.scalar(select(VicidialCanaryRun).where(VicidialCanaryRun.approval_id == approval_id))
    if existing:
        raise HTTPException(409, "one-lead canary run already exists")
    auth = CanaryAuthorization(approval.campaign_id, approval.list_id, approval.maintenance_window_start, approval.maintenance_window_end, approval.authorization_reference or "", approval.approved_by or "")
    validate_authorization(auth)
    enforce_window(datetime.now(UTC), start=auth.maintenance_start, end=auth.maintenance_end)
    enforce_limits(call_count=0, lead_count=0)
    run = VicidialCanaryRun(tenant_id=tenant_header, approval_id=approval_id, assignment_item_id=body.assignment_item_id, allowlisted_phone_hash=phone_hash(body.test_phone), agent_reference=body.agent_reference, carrier_check=body.carrier_check, dialing_window_check=body.dialing_window_check)
    db.add(run)
    await db.flush()
    db.add(VicidialCanaryEvent(canary_run_id=run.id, event_type="CANARY_AUTHORIZED", payload_safe={"phone_allowlisted": True, "max_calls": 1}, correlation_id=str(uuid4())))
    await db.commit()
    return {"run_id": str(run.id), "status": run.status, "phone_stored": "hash_only", "dialing_enabled": False}
