"""Authenticated staging campaign design API."""
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import BearerAuthError, authenticated_service_subject
from app.core.campaign_design import (
    CampaignApprovalInput,
    CampaignDesignInput,
    CampaignDesignService,
    DesignConflict,
    PostgresDesignStore,
)
from app.core.config import settings
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/campaign-designs", tags=["campaign-design"])


def approval_service_subject(
    authorization: Annotated[str, Header(alias="Authorization")],
) -> str:
    """Bind approval provenance to the verified calling service, not a claim."""
    try:
        return authenticated_service_subject(
            authorization, settings.middleware_secret
        )
    except BearerAuthError as exc:
        raise HTTPException(401, str(exc)) from exc


@router.post("/preview")
async def preview(
    request: CampaignDesignInput,
    business_unit: Annotated[
        str, Header(alias="X-Business-Unit", min_length=2, max_length=16)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
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
    request: CampaignApprovalInput,
    actor: Annotated[str, Depends(approval_service_subject)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    correlation_id: Annotated[
        str, Header(alias="X-Correlation-ID", min_length=8, max_length=128)
    ],
    db: Annotated[AsyncSession, Depends(get_session)],
):
    if not settings.campaign_design_enabled:
        raise HTTPException(503, "campaign design is disabled")
    try:
        return await CampaignDesignService(PostgresDesignStore(db)).approve(
            integration_uuid,
            request.design_revision,
            request.manifest_hash,
            actor,
            request.reason,
            idempotency_key,
            correlation_id,
        )
    except DesignConflict as exc:
        raise HTTPException(409, str(exc)) from exc
