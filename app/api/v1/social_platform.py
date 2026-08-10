from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.platform.domain import (
    CampaignState,
    InvalidCampaignTransition,
    provider_health_score,
    lead_identity_hash,
    normalize_analytics,
    safe_location_reference,
    score_lead,
    validate_media,
)
from app.platform.ai import optimization_recommendation
from app.platform.repository import PlatformRepository

router = APIRouter(prefix="/api/v1", tags=["social-platform"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CampaignCreate(StrictModel):
    tenant_id: UUID
    name: str = Field(min_length=1, max_length=255)
    objective: str = Field(min_length=1, max_length=2000)


class CampaignTransition(StrictModel):
    tenant_id: UUID
    target: CampaignState
    reason: str = Field(min_length=1, max_length=1000)


class ContentCreate(StrictModel):
    tenant_id: UUID
    network: Literal["facebook", "instagram", "linkedin", "x", "tiktok", "youtube"]
    language: Literal["en", "es", "fr", "ht"]
    text: str = Field(min_length=1, max_length=10000)
    ai_generated: bool = False
    ai_model_reference: str | None = Field(None, max_length=255)
    risk_status: Literal["PASS", "REVIEW_REQUIRED", "BLOCKED"]


class Approval(StrictModel):
    tenant_id: UUID
    version: int = Field(ge=1)
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=1, max_length=1000)


class LeadIntelligenceRequest(StrictModel):
    tenant_id: UUID
    campaign_id: UUID | None = None
    source_event_id: str = Field(min_length=1, max_length=255)
    signals: dict[str, bool] = Field(default_factory=dict)
    email: str | None = Field(None, max_length=320)
    phone: str | None = Field(None, max_length=64)
    social_profile: str | None = Field(None, max_length=1000)
    consent_status: Literal["UNKNOWN", "GRANTED", "DENIED"] = "UNKNOWN"
    dnc_status: Literal["UNKNOWN", "CLEAR", "BLOCKED"] = "UNKNOWN"


class AnalyticsRequest(StrictModel):
    metrics: dict[str, Any]
    baseline: dict[str, float] = Field(default_factory=dict)


class MediaRegister(StrictModel):
    tenant_id: UUID
    content_type: str = Field(max_length=128)
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    checksum: str = Field(min_length=64, max_length=64)
    storage_backend: Literal["local", "object"]
    location_reference: str = Field(min_length=1, max_length=1000)
    expires_at: datetime | None = None


class OdooDryRunRequest(StrictModel):
    tenant_id: UUID
    lead_intelligence_id: UUID
    fields: dict[str, Any] = Field(default_factory=dict)


class ReplayRequest(StrictModel):
    reason: str = Field(min_length=1, max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=255)


def _require(permission: str, supplied: str | None) -> str:
    permissions = {item.strip() for item in (supplied or "").split(",") if item.strip()}
    if permission not in permissions and "social.admin" not in permissions:
        raise HTTPException(
            403,
            {
                "code": "SOCIAL_PERMISSION_DENIED",
                "message": f"Permission {permission} is required",
            },
        )
    return "machine" if not supplied else "authenticated-client"


def _correlation(request: Request) -> str:
    return request.headers.get("X-Correlation-ID") or str(uuid4())


@router.post("/campaigns", status_code=201)
async def create_campaign(
    body: CampaignCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    actor = _require("social.ops.campaigns", permissions)
    return await PlatformRepository(session).create_campaign(
        tenant_id=body.tenant_id,
        name=body.name,
        objective=body.objective,
        correlation_id=_correlation(request),
        actor=actor,
    )


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: UUID,
    tenant_id: UUID = Query(),
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    _require("social.ops.read", permissions)
    value = await PlatformRepository(session).get_campaign(campaign_id, tenant_id)
    if not value:
        raise HTTPException(
            404,
            {"code": "SOCIAL_CAMPAIGN_NOT_FOUND", "message": "Campaign was not found"},
        )
    return value


@router.post("/campaigns/{campaign_id}/transitions")
async def transition_campaign(
    campaign_id: UUID,
    body: CampaignTransition,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    actor = _require("social.ops.campaigns", permissions)
    try:
        value = await PlatformRepository(session).transition(
            campaign_id=campaign_id,
            tenant_id=body.tenant_id,
            target=body.target,
            reason=body.reason,
            correlation_id=_correlation(request),
            actor=actor,
        )
    except InvalidCampaignTransition as exc:
        raise HTTPException(
            409, {"code": "SOCIAL_CAMPAIGN_TRANSITION_INVALID", "message": str(exc)}
        ) from exc
    if not value:
        raise HTTPException(
            404,
            {"code": "SOCIAL_CAMPAIGN_NOT_FOUND", "message": "Campaign was not found"},
        )
    return value


@router.post("/campaigns/{campaign_id}/content", status_code=201)
async def add_content(
    campaign_id: UUID,
    body: ContentCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    actor = _require("social.ops.campaigns", permissions)
    value = await PlatformRepository(session).add_content(
        campaign_id=campaign_id,
        tenant_id=body.tenant_id,
        network=body.network,
        language=body.language,
        text_value=body.text,
        ai_generated=body.ai_generated,
        ai_model_reference=body.ai_model_reference,
        risk_status=body.risk_status,
        correlation_id=_correlation(request),
        actor=actor,
    )
    if not value:
        raise HTTPException(
            404,
            {"code": "SOCIAL_CAMPAIGN_NOT_FOUND", "message": "Campaign was not found"},
        )
    return value


@router.post("/campaign-content/{content_id}/approval")
async def approve_content(
    content_id: UUID,
    body: Approval,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    actor = _require("social.ops.campaigns", permissions)
    try:
        value = await PlatformRepository(session).approve_content(
            content_id=content_id,
            tenant_id=body.tenant_id,
            version=body.version,
            decision=body.decision,
            reason=body.reason,
            actor=actor,
            correlation_id=_correlation(request),
        )
    except ValueError as exc:
        raise HTTPException(
            409, {"code": str(exc), "message": "Blocked content cannot be approved"}
        ) from exc
    if not value:
        raise HTTPException(
            404,
            {
                "code": "SOCIAL_CONTENT_NOT_FOUND",
                "message": "Content version was not found",
            },
        )
    return value


@router.get("/social/providers/health")
async def provider_health(
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> list[dict]:
    _require("social.ops.read", permissions)
    postly = provider_health_score(
        reachable=False,
        authenticated=bool(settings.postiz_api_key_file),
        latency_ms=9999,
        error_rate=1.0,
        poll_lag_seconds=9999,
    )
    return [
        {
            "provider": "postly",
            "configured": bool(
                settings.postiz_internal_base_url and settings.postiz_api_key_file
            ),
            "enabled": settings.social_integration_enabled,
            "score": postly.score,
            "status": "DISABLED"
            if not settings.social_integration_enabled
            else postly.status,
            "components": postly.components,
        },
        {
            "provider": "hootsuite",
            "configured": bool(
                settings.hootsuite_client_id_file
                and settings.hootsuite_client_secret_file
            ),
            "enabled": False,
            "score": 0,
            "status": "NOT_CONFIGURED",
        },
    ]


@router.get("/ops/social/config")
async def social_config(
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    _require("social.ops.security", permissions)
    return {
        "social_publish_enabled": settings.social_publish_enabled,
        "social_production_canary_enabled": settings.social_production_canary_enabled,
        "social_odoo_write_enabled": settings.social_odoo_write_enabled,
        "automatic_provider_failover": settings.social_automatic_provider_failover_enabled,
        "automatic_dual_publish": settings.social_automatic_dual_publish_enabled,
        "global_kill_switch": settings.social_global_kill_switch,
        "postly_kill_switch": settings.social_provider_postly_kill_switch,
        "n8n_delivery_kill_switch": settings.social_n8n_delivery_kill_switch,
        "campaign_automation_kill_switch": settings.social_campaign_automation_kill_switch,
        "ai_generation_kill_switch": settings.social_ai_generation_kill_switch,
    }


@router.get("/ops/social/deadletters")
async def deadletters(
    tenant_id: UUID = Query(),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> list[dict]:
    _require("social.ops.deadletter", permissions)
    return await PlatformRepository(session).list_dead_letters(tenant_id, limit)


@router.post("/leads/intelligence", status_code=202)
async def lead_intelligence(
    body: LeadIntelligenceRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    _require("social.ops.read", permissions)
    score = score_lead(body.signals)
    return await PlatformRepository(session).store_lead_intelligence(
        tenant_id=body.tenant_id,
        campaign_id=body.campaign_id,
        source_event_id=body.source_event_id,
        category=score.category.value,
        quality_score=score.score,
        factors=score.factors,
        identity_hash=lead_identity_hash(
            email=body.email, phone=body.phone, profile=body.social_profile
        ),
        consent_status=body.consent_status,
        dnc_status=body.dnc_status,
        correlation_id=_correlation(request),
    )


@router.post("/social/analytics/normalize")
async def analytics_normalize(
    body: AnalyticsRequest,
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    _require("social.analytics.read", permissions)
    normalized = normalize_analytics(body.metrics)
    return {
        "metrics": normalized,
        "recommendation": optimization_recommendation(
            {
                key: float(value)
                for key, value in normalized.items()
                if value is not None
            },
            body.baseline,
        ),
        "automatic_change": False,
    }


@router.post("/ops/social/media", status_code=201)
async def media_register(
    body: MediaRegister,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    _require("social.ops.accounts", permissions)
    validate_media(
        content_type=body.content_type,
        filename=body.filename,
        size=body.size_bytes,
        checksum=body.checksum,
        maximum_bytes=settings.social_media_max_bytes,
    )
    location = safe_location_reference(body.location_reference)
    if body.storage_backend == "object":
        raise HTTPException(
            503,
            {
                "code": "SOCIAL_OBJECT_STORAGE_NOT_CONFIGURED",
                "message": "Object storage is not configured",
            },
        )
    return await PlatformRepository(session).register_media(
        tenant_id=body.tenant_id,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        checksum=body.checksum,
        storage_backend=body.storage_backend,
        location_reference=location,
        expires_at=body.expires_at,
    )


@router.post("/odoo/leads/dry-run")
async def odoo_dry_run(
    body: OdooDryRunRequest,
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    _require("social.ops.read", permissions)
    return {
        "tenant_id": body.tenant_id,
        "lead_intelligence_id": body.lead_intelligence_id,
        "dry_run": True,
        "write_enabled": False,
        "validated_field_names": sorted(body.fields),
        "command_dispatched": False,
    }


@router.post("/ops/social/deadletters/{job_id}/replay")
async def deadletter_replay(
    job_id: UUID,
    body: ReplayRequest,
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    _require("social.ops.retry", permissions)
    raise HTTPException(
        409,
        {
            "code": "SOCIAL_DEADLETTER_REPLAY_DISABLED",
            "message": "Automatic and operator replay remain disabled until reconciliation proves safety",
            "job_id": str(job_id),
        },
    )
