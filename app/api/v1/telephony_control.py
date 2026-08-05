"""Campaign, security, usage, and release control-plane staging APIs."""

from datetime import UTC, datetime
from typing import Any
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.core.config import settings
from app.core.telephony_campaigns import LeadEligibility, lead_is_eligible
from app.core.telephony_commercial import TelephonyUsage, valid_usage

router = APIRouter(prefix="/api/v1/telephony-control", tags=["telephony-control"])


class CampaignEligibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    campaign_id: str = Field(min_length=1, max_length=128)
    normalized_phone: str = Field(min_length=7, max_length=32)
    consent_state: str = Field(min_length=1, max_length=24)
    suppressed: bool = False


class UsageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    usage_type: str = Field(min_length=1, max_length=64)
    quantity: int = Field(ge=0)
    unit: str = Field(min_length=1, max_length=32)
    idempotency_key: str = Field(min_length=8, max_length=255)


@router.get("/health")
async def health(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not tenant_id:
        raise HTTPException(403, "tenant scope required")
    return {"tenant_id": tenant_id, "campaign_activation": False, "live_dialing": False, "bulk_outbound": False, "ami_public": False, "ari_public": False}


@router.post("/campaigns/eligibility")
async def eligibility(body: CampaignEligibilityRequest) -> dict[str, Any]:
    eligible = lead_is_eligible(LeadEligibility(**body.model_dump()), now=datetime.now(UTC))
    return {"eligible": eligible, "dialing": False, "reason": "eligible_for_staging_only" if eligible else "consent_suppression_or_scope_failed"}


@router.post("/usage", status_code=202)
async def usage(body: UsageRequest) -> dict[str, Any]:
    if not settings.telephony_usage_platform_enabled:
        raise HTTPException(404, "telephony usage platform unavailable")
    record = TelephonyUsage(**body.model_dump())
    if not valid_usage(record):
        raise HTTPException(400, "invalid usage record")
    return {"state": "RECEIVED", "idempotency_key": body.idempotency_key, "middleware_delivery": "STAGING"}


@router.post("/releases/{release_id}/validate")
async def validate_release(release_id: str) -> dict[str, Any]:
    if not settings.telephony_release_platform_enabled:
        raise HTTPException(404, "telephony release platform unavailable")
    return {"release_id": release_id, "state": "STAGING_VALIDATED", "production_activation": False, "carrier_changes": False, "trunk_changes": False}
