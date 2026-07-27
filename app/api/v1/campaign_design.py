"""Authenticated staging campaign design API."""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.campaign_design import (
    CampaignDesignInput, CampaignDesignService, DesignConflict, PostgresDesignStore,
)
from app.db.session import get_session
from app.core.config import settings

router = APIRouter(prefix="/api/v1/campaign-designs", tags=["campaign-design"])


@router.post("/preview")
async def preview(
    request: CampaignDesignInput,
    business_unit: str = Header(..., alias="X-Business-Unit"),
    db: AsyncSession = Depends(get_session),
):
    if not settings.campaign_design_enabled:
        raise HTTPException(503, "campaign design is disabled")
    if business_unit.upper() != request.business_unit:
        raise HTTPException(403, "cross-business-unit preview denied")
    try:
        return await CampaignDesignService(PostgresDesignStore(db)).consume(request)
    except DesignConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{integration_uuid}/approve")
async def approve(
    integration_uuid: str,
    actor: str = Header(..., alias="X-Approval-Actor"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    db: AsyncSession = Depends(get_session),
):
    if not settings.campaign_design_enabled:
        raise HTTPException(503, "campaign design is disabled")
    try:
        return await CampaignDesignService(PostgresDesignStore(db)).approve(
            integration_uuid, actor, correlation_id
        )
    except DesignConflict as exc:
        raise HTTPException(409, str(exc)) from exc
