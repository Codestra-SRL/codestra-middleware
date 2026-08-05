from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.revops import RevOpsPolicyError, validate_campaign_state, validate_opportunity_state
from app.db.models import RevOpsCampaign, RevOpsLead, RevOpsOpportunity
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/revops", tags=["revops"])


def require_revops(tenant_id: str, role: str) -> None:
    if not tenant_id or not role:
        raise HTTPException(403, "RevOps authorization required")
    if not settings.revops_platform_enabled:
        raise HTTPException(404, "RevOps platform unavailable")


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_revops(tenant_id, role)
    return {"tenant_id": tenant_id, "status": "read_model_pending", "ai_decisions_advisory": True}


@router.post("/leads", status_code=202)
async def create_lead(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_revops(tenant_id, role)
    lead = RevOpsLead(tenant_id=tenant_id, display_name=str(body.get("display_name", "")), source=str(body.get("source", "")), idempotency_key=str(body.get("idempotency_key", uuid4())))
    if not lead.display_name:
        raise HTTPException(422, "display_name required")
    db.add(lead)
    await db.commit()
    return {"lead_id": str(lead.id), "status": "NEW"}


@router.post("/opportunities", status_code=202)
async def create_opportunity(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_revops(tenant_id, role)
    try:
        state = validate_opportunity_state(str(body.get("status", "NEW")))
    except RevOpsPolicyError as exc:
        raise HTTPException(422, str(exc)) from exc
    opportunity = RevOpsOpportunity(tenant_id=tenant_id, lead_id=str(body.get("lead_id", "")), name=str(body.get("name", "")), status=state, idempotency_key=str(body.get("idempotency_key", uuid4())))
    if not opportunity.lead_id or not opportunity.name:
        raise HTTPException(422, "lead_id and name required")
    db.add(opportunity)
    await db.commit()
    return {"opportunity_id": str(opportunity.id), "status": opportunity.status}


@router.post("/campaigns", status_code=202)
async def create_campaign(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_revops(tenant_id, role)
    try:
        state = validate_campaign_state(str(body.get("status", "DRAFT")))
    except RevOpsPolicyError as exc:
        raise HTTPException(422, str(exc)) from exc
    campaign = RevOpsCampaign(tenant_id=tenant_id, name=str(body.get("name", "")), status=state, idempotency_key=str(body.get("idempotency_key", uuid4())))
    if not campaign.name:
        raise HTTPException(422, "name required")
    db.add(campaign)
    await db.commit()
    return {"campaign_id": str(campaign.id), "status": campaign.status}
