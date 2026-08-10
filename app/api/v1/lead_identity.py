from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_session
from app.leads.domain import (
    build_utm,
    normalize_domain,
    normalize_email,
    normalize_phone,
    next_best_action,
    quality_score,
)
from app.leads.repository import LeadRepository
from app.leads.metrics import (
    attribution_calculations,
    consent_blocks,
    dnc_blocks,
    identity_resolution,
    lead_created,
    lead_deduped,
    lead_scores,
    next_actions,
    revenue_events,
)

router = APIRouter(prefix="/api/v1", tags=["lead-identity-revenue"])

ATTRIBUTION_GROUP_QUERIES = {
    "campaigns": "SELECT a.campaign_id AS key,a.currency,SUM(a.attributed_amount) AS attributed_amount,COUNT(*) AS allocation_count FROM attribution_allocations a JOIN attribution_calculations c ON c.id=a.calculation_id JOIN revenue_events r ON r.id=c.revenue_event_id JOIN lead_campaign_touches t ON t.id=a.touch_id WHERE r.tenant_id=:tenant AND r.is_synthetic=false AND c.superseded=false GROUP BY a.campaign_id,a.currency ORDER BY attributed_amount DESC NULLS LAST LIMIT 500",
    "content": "SELECT a.content_id AS key,a.currency,SUM(a.attributed_amount) AS attributed_amount,COUNT(*) AS allocation_count FROM attribution_allocations a JOIN attribution_calculations c ON c.id=a.calculation_id JOIN revenue_events r ON r.id=c.revenue_event_id JOIN lead_campaign_touches t ON t.id=a.touch_id WHERE r.tenant_id=:tenant AND r.is_synthetic=false AND c.superseded=false GROUP BY a.content_id,a.currency ORDER BY attributed_amount DESC NULLS LAST LIMIT 500",
    "networks": "SELECT t.network AS key,a.currency,SUM(a.attributed_amount) AS attributed_amount,COUNT(*) AS allocation_count FROM attribution_allocations a JOIN attribution_calculations c ON c.id=a.calculation_id JOIN revenue_events r ON r.id=c.revenue_event_id JOIN lead_campaign_touches t ON t.id=a.touch_id WHERE r.tenant_id=:tenant AND r.is_synthetic=false AND c.superseded=false GROUP BY t.network,a.currency ORDER BY attributed_amount DESC NULLS LAST LIMIT 500",
    "providers": "SELECT t.provider AS key,a.currency,SUM(a.attributed_amount) AS attributed_amount,COUNT(*) AS allocation_count FROM attribution_allocations a JOIN attribution_calculations c ON c.id=a.calculation_id JOIN revenue_events r ON r.id=c.revenue_event_id JOIN lead_campaign_touches t ON t.id=a.touch_id WHERE r.tenant_id=:tenant AND r.is_synthetic=false AND c.superseded=false GROUP BY t.provider,a.currency ORDER BY attributed_amount DESC NULLS LAST LIMIT 500",
    "leads": "SELECT r.lead_id AS key,a.currency,SUM(a.attributed_amount) AS attributed_amount,COUNT(*) AS allocation_count FROM attribution_allocations a JOIN attribution_calculations c ON c.id=a.calculation_id JOIN revenue_events r ON r.id=c.revenue_event_id JOIN lead_campaign_touches t ON t.id=a.touch_id WHERE r.tenant_id=:tenant AND r.is_synthetic=false AND c.superseded=false GROUP BY r.lead_id,a.currency ORDER BY attributed_amount DESC NULLS LAST LIMIT 500",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResolveIdentity(StrictModel):
    tenant_id: UUID
    display_name: str | None = Field(None, max_length=255)
    email: str | None = Field(None, max_length=320)
    phone: str | None = Field(None, max_length=64)
    country_hint: str | None = Field(None, min_length=2, max_length=2)
    social_provider: str | None = Field(None, max_length=32)
    social_network: str | None = Field(None, max_length=32)
    social_profile_id: str | None = Field(None, max_length=255)

    @model_validator(mode="after")
    def has_key(self):
        if not any((self.email, self.phone, self.social_profile_id)):
            raise ValueError("at least one deterministic identity key is required")
        social = (self.social_provider, self.social_network, self.social_profile_id)
        if any(social) and not all(social):
            raise ValueError(
                "social identity requires provider, network, and profile ID"
            )
        return self


class MergeIdentity(StrictModel):
    tenant_id: UUID
    source_id: UUID
    target_id: UUID
    reason: str = Field(min_length=1, max_length=1000)


class ResolveCompany(StrictModel):
    tenant_id: UUID
    legal_name: str | None = Field(None, max_length=255)
    display_name: str | None = Field(None, max_length=255)
    domain: str | None = Field(None, max_length=1000)
    registration_number: str | None = Field(None, max_length=128)
    country: str | None = Field(None, min_length=2, max_length=2)

    @model_validator(mode="after")
    def has_key(self):
        if not self.domain and not self.registration_number:
            raise ValueError(
                "company resolution requires domain or registration number"
            )
        return self


class LeadCreate(StrictModel):
    tenant_id: UUID
    person_id: UUID | None = None
    company_id: UUID | None = None
    campaign_id: UUID | None = None
    source: str = Field(min_length=1, max_length=64)
    consent_status: Literal[
        "UNKNOWN", "NOT_REQUIRED", "PENDING", "GRANTED", "REVOKED", "EXPIRED"
    ] = "UNKNOWN"
    dnc_status: Literal[
        "CLEAR",
        "INTERNAL_DNC",
        "NATIONAL_DNC",
        "CUSTOMER_REQUEST",
        "LEGAL_BLOCK",
        "UNKNOWN",
    ] = "UNKNOWN"

    @model_validator(mode="after")
    def has_identity(self):
        if not self.person_id and not self.company_id:
            raise ValueError("lead requires person or company identity")
        return self


class InteractionCreate(StrictModel):
    tenant_id: UUID
    interaction_type: Literal[
        "SOCIAL_COMMENT",
        "SOCIAL_MESSAGE",
        "FORM_SUBMISSION",
        "WEBSITE_VISIT",
        "EMAIL_EVENT",
        "PHONE_EVENT",
        "CALL_REQUEST",
        "CALL_RESULT",
        "APPOINTMENT",
        "ODOO_ACTIVITY",
        "CAMPAIGN_TOUCH",
        "CONTENT_CLICK",
        "AI_CLASSIFICATION",
        "MANUAL_NOTE",
        "OTHER",
    ]
    source: str = Field(min_length=1, max_length=64)
    source_event_id: str = Field(min_length=1, max_length=255)
    campaign_id: UUID | None = None
    content_id: UUID | None = None
    occurred_at: datetime
    safe_payload: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )


class UnmergeIdentity(StrictModel):
    tenant_id: UUID
    source_id: UUID
    reason: str = Field(min_length=1, max_length=1000)


class NextActionRequest(StrictModel):
    tenant_id: UUID
    intent: Literal[
        "BUYING_INTENT",
        "INFORMATION_REQUEST",
        "SUPPORT",
        "COMPLAINT",
        "PARTNERSHIP",
        "JOB_SEEKER",
        "VENDOR",
        "SPAM",
        "UNKNOWN",
    ]
    score_components: dict[str, int] = Field(default_factory=dict)
    has_phone: bool = False
    has_email: bool = False
    has_social: bool = False


class Feedback(StrictModel):
    tenant_id: UUID
    decision_id: UUID
    outcome: Literal[
        "CONTACT",
        "RESPONSE",
        "APPOINTMENT",
        "OPPORTUNITY",
        "SALE",
        "NO_RESPONSE",
        "OPT_OUT",
        "COMPLAINT",
    ]


class RevenueCreate(StrictModel):
    tenant_id: UUID
    lead_id: UUID
    event_type: Literal[
        "OPPORTUNITY_CREATED",
        "APPOINTMENT_BOOKED",
        "SALE_WON",
        "PAYMENT_RECEIVED",
        "SUBSCRIPTION_STARTED",
        "SUBSCRIPTION_RENEWED",
        "REFUND",
        "CANCELLATION",
    ]
    amount: Decimal | None = None
    currency: str | None = Field(None, min_length=3, max_length=3)
    source_system: str = Field(min_length=1, max_length=64)
    external_reference: str = Field(min_length=1, max_length=255)
    occurred_at: datetime
    is_synthetic: bool = False

    @model_validator(mode="after")
    def monetary_pair(self):
        if (self.amount is None) != (self.currency is None):
            raise ValueError("amount and currency must be supplied together")
        synthetic_source = self.source_system.upper().startswith("SYNTHETIC_")
        if synthetic_source != self.is_synthetic:
            raise ValueError(
                "synthetic revenue source and is_synthetic marker must agree"
            )
        return self


def metric_source(value: str) -> str:
    normalized = value.upper()
    return normalized if normalized in {"SOCIAL", "WEB", "EMAIL", "OTHER"} else "OTHER"


class AttributionRequest(StrictModel):
    tenant_id: UUID
    model: Literal[
        "FIRST_TOUCH", "LAST_TOUCH", "LINEAR", "POSITION_BASED", "TIME_DECAY"
    ]


class TouchCreate(StrictModel):
    tenant_id: UUID
    lead_id: UUID
    campaign_id: UUID
    content_id: UUID | None = None
    network: str | None = Field(None, max_length=32)
    provider: str | None = Field(None, max_length=32)
    source: str = Field(min_length=1, max_length=64)
    source_event_id: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=64)
    occurred_at: datetime


def require(permission: str, supplied: str | None) -> str:
    values = {item.strip() for item in (supplied or "").split(",") if item.strip()}
    if permission not in values and "lead.admin" not in values:
        raise HTTPException(
            403,
            {
                "code": "LEAD_PERMISSION_DENIED",
                "message": f"Permission {permission} is required",
            },
        )
    return "authenticated-client"


def correlation(request: Request) -> str:
    return request.headers.get("X-Correlation-ID") or str(uuid4())


@router.post("/identity/resolve")
async def resolve(
    body: ResolveIdentity,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("identity.review", permissions)
    if not settings.identity_graph_enabled:
        raise HTTPException(
            503,
            {
                "code": "IDENTITY_GRAPH_DISABLED",
                "message": "Identity graph is disabled",
            },
        )
    email = normalize_email(body.email) if body.email else None
    phone, status = (
        normalize_phone(body.phone, body.country_hint)
        if body.phone
        else (None, "ABSENT")
    )
    social = None
    if body.social_profile_id:
        if body.social_provider is None or body.social_network is None:
            raise HTTPException(
                422,
                {
                    "code": "SOCIAL_IDENTITY_INVALID",
                    "message": "Social identity is incomplete",
                },
            )
        social = (body.social_provider, body.social_network, body.social_profile_id)
    result = await LeadRepository(session).resolve_person(
        tenant_id=body.tenant_id,
        display_name=body.display_name,
        email=email,
        phone=phone,
        social=social,
        correlation_id=correlation(request),
    )
    result["phone_normalization_status"] = status
    identity_resolution.labels(
        result="created" if result.get("created") else "matched",
        confidence=str(result.get("confidence", "UNKNOWN")),
    ).inc()
    return result


@router.get("/identity/persons/{person_id}")
async def person(
    person_id: UUID,
    tenant_id: UUID = Query(),
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("identity.read", permissions)
    value = await LeadRepository(session).get_person(tenant_id, person_id)
    if not value:
        raise HTTPException(
            404, {"code": "IDENTITY_NOT_FOUND", "message": "Identity was not found"}
        )
    return value


@router.post("/identity/merge")
async def merge(
    body: MergeIdentity,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    actor = require("identity.merge", permissions)
    try:
        decision = await LeadRepository(session).merge_person(
            tenant_id=body.tenant_id,
            source=body.source_id,
            target=body.target_id,
            actor=actor,
            reason=body.reason,
            correlation_id=correlation(request),
        )
    except ValueError as exc:
        raise HTTPException(
            409, {"code": str(exc), "message": "Identity merge was rejected"}
        ) from exc
    return {
        "decision_id": decision,
        "source_id": body.source_id,
        "target_id": body.target_id,
        "reversible": True,
    }


@router.post("/identity/companies/resolve")
async def resolve_company(
    body: ResolveCompany,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("identity.review", permissions)
    if not settings.identity_graph_enabled:
        raise HTTPException(
            503,
            {
                "code": "IDENTITY_GRAPH_DISABLED",
                "message": "Identity graph is disabled",
            },
        )
    return await LeadRepository(session).resolve_company(
        tenant_id=body.tenant_id,
        legal_name=body.legal_name,
        display_name=body.display_name,
        domain=normalize_domain(body.domain) if body.domain else None,
        registration_number=body.registration_number,
        country=body.country.upper() if body.country else None,
        correlation_id=correlation(request),
    )


@router.get("/identity/companies/{company_id}")
async def company(
    company_id: UUID,
    tenant_id: UUID = Query(),
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("identity.read", permissions)
    value = await LeadRepository(session).get_company(tenant_id, company_id)
    if not value:
        raise HTTPException(
            404,
            {"code": "IDENTITY_NOT_FOUND", "message": "Company identity was not found"},
        )
    return value


@router.get("/identity/{identity_id}/timeline")
async def identity_timeline(
    identity_id: UUID,
    tenant_id: UUID = Query(),
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> list[dict]:
    require("identity.read", permissions)
    rows = (
        (
            await session.execute(
                text(
                    "SELECT i.id,i.interaction_type,i.source,i.source_event_id,i.campaign_id,i.content_id,i.correlation_id,i.occurred_at FROM lead_interactions i JOIN lead_records l ON l.id=i.lead_id WHERE i.tenant_id=:tenant AND (l.person_id=:identity OR l.company_id=:identity) ORDER BY i.occurred_at,i.id LIMIT 500"
                ),
                {"tenant": tenant_id, "identity": identity_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.post("/leads", status_code=201)
async def create_lead(
    body: LeadCreate,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("lead.write", permissions)
    if not settings.lead_intelligence_enabled:
        raise HTTPException(
            503,
            {
                "code": "LEAD_INTELLIGENCE_DISABLED",
                "message": "Lead intelligence is disabled",
            },
        )
    lead_id, created = await LeadRepository(session).upsert_lead(
        tenant_id=body.tenant_id,
        person_id=body.person_id,
        company_id=body.company_id,
        campaign_id=body.campaign_id,
        source=body.source,
        consent=body.consent_status,
        dnc=body.dnc_status,
    )
    (lead_created if created else lead_deduped).labels(
        source=metric_source(body.source)
    ).inc()
    return {
        "lead_id": lead_id,
        "created": created,
        "deduplicated": not created,
        "external_command_dispatched": False,
    }


@router.post("/leads/{lead_id}/interactions", status_code=201)
async def add_interaction(
    lead_id: UUID,
    body: InteractionCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("lead.write", permissions)
    exists = (
        await session.execute(
            text("SELECT 1 FROM lead_records WHERE id=:id AND tenant_id=:tenant"),
            {"id": lead_id, "tenant": body.tenant_id},
        )
    ).scalar_one_or_none()
    if not exists:
        raise HTTPException(
            404, {"code": "LEAD_NOT_FOUND", "message": "Lead was not found"}
        )
    interaction_id, created = await LeadRepository(session).add_interaction(
        tenant_id=body.tenant_id,
        lead_id=lead_id,
        interaction_type=body.interaction_type,
        source=body.source,
        source_event_id=body.source_event_id,
        campaign_id=body.campaign_id,
        content_id=body.content_id,
        correlation_id=correlation(request),
        occurred_at=body.occurred_at,
        safe_payload=body.safe_payload,
    )
    return {
        "interaction_id": interaction_id,
        "created": created,
        "deduplicated": not created,
    }


@router.post("/identity/unmerge")
async def unmerge(
    body: UnmergeIdentity,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    actor = require("identity.merge", permissions)
    try:
        decision = await LeadRepository(session).unmerge_person(
            tenant_id=body.tenant_id,
            source=body.source_id,
            actor=actor,
            reason=body.reason,
            correlation_id=correlation(request),
        )
    except ValueError as exc:
        raise HTTPException(
            409, {"code": str(exc), "message": "Identity reversal was rejected"}
        ) from exc
    return {"decision_id": decision, "source_id": body.source_id, "reversed": True}


@router.post("/leads/{lead_id}/next-action")
async def decide_action(
    lead_id: UUID,
    body: NextActionRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    actor = require("lead.score", permissions)
    if not settings.next_best_action_enabled:
        raise HTTPException(
            503,
            {
                "code": "NEXT_BEST_ACTION_DISABLED",
                "message": "Next-best-action engine is disabled",
            },
        )
    lead = (
        (
            await session.execute(
                text(
                    "SELECT consent_status,dnc_status FROM lead_records WHERE id=:id AND tenant_id=:tenant"
                ),
                {"id": lead_id, "tenant": body.tenant_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not lead:
        raise HTTPException(
            404, {"code": "LEAD_NOT_FOUND", "message": "Lead was not found"}
        )
    score, components = quality_score(body.score_components)
    lead_scores.observe(score)
    decision = next_best_action(
        dnc=lead["dnc_status"],
        consent=lead["consent_status"],
        intent=body.intent,
        score=score,
        phone=body.has_phone,
        email=body.has_email,
        social=body.has_social,
    )
    decision_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO next_action_decisions(id,tenant_id,lead_id,action,eligible_for_contact,reasons,rule_version,actor,correlation_id) VALUES(:id,:tenant,:lead,:action,:eligible,:reasons,'n7-v1',:actor,:correlation)"
        ),
        {
            "id": decision_id,
            "tenant": body.tenant_id,
            "lead": lead_id,
            "action": decision.action.value,
            "eligible": decision.eligible_for_contact,
            "reasons": json.dumps(list(decision.reasons)),
            "actor": actor,
            "correlation": correlation(request),
        },
    )
    await session.execute(
        text(
            "UPDATE lead_records SET current_score=:score,next_best_action=:action,updated_at=now() WHERE id=:lead"
        ),
        {"score": score, "action": decision.action.value, "lead": lead_id},
    )
    await session.commit()
    next_actions.labels(
        action=decision.action.value,
        eligible=str(decision.eligible_for_contact).lower(),
    ).inc()
    if "DNC_BLOCK" in decision.reasons:
        dnc_blocks.labels(channel="all").inc()
    if "CONSENT_NOT_GRANTED" in decision.reasons:
        consent_blocks.labels(channel="all").inc()
    return {
        "decision_id": decision_id,
        "action": decision.action,
        "eligible_for_contact": decision.eligible_for_contact,
        "reasons": decision.reasons,
        "score": score,
        "components": components,
        "automatic_contact": False,
    }


@router.get("/leads/{lead_id}/next-action")
async def get_action(
    lead_id: UUID,
    tenant_id: UUID = Query(),
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("lead.read", permissions)
    row = (
        (
            await session.execute(
                text(
                    "SELECT id,action,eligible_for_contact,reasons,rule_version,created_at FROM next_action_decisions WHERE lead_id=:lead AND tenant_id=:tenant ORDER BY created_at DESC LIMIT 1"
                ),
                {"lead": lead_id, "tenant": tenant_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(
            404,
            {"code": "NEXT_ACTION_NOT_FOUND", "message": "No action decision exists"},
        )
    return dict(row)


@router.post("/leads/{lead_id}/action-feedback", status_code=201)
async def feedback(
    lead_id: UUID,
    body: Feedback,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    actor = require("lead.write", permissions)
    feedback_id = uuid4()
    result = await session.execute(
        text(
            "INSERT INTO action_feedback(id,tenant_id,lead_id,decision_id,outcome,actor) SELECT :id,:tenant,:lead,:decision,:outcome,:actor WHERE EXISTS (SELECT 1 FROM next_action_decisions WHERE id=:decision AND tenant_id=:tenant AND lead_id=:lead) RETURNING id"
        ),
        {
            "id": feedback_id,
            "tenant": body.tenant_id,
            "lead": lead_id,
            "decision": body.decision_id,
            "outcome": body.outcome,
            "actor": actor,
        },
    )
    if result.scalar_one_or_none() is None:
        await session.rollback()
        raise HTTPException(
            404, {"code": "NEXT_ACTION_NOT_FOUND", "message": "Decision was not found"}
        )
    await session.commit()
    return {"feedback_id": feedback_id, "training_automatic": False}


@router.post("/analytics/attribution/revenue", status_code=201)
async def revenue(
    body: RevenueCreate,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("revenue.write", permissions)
    if not settings.revenue_event_sync_enabled:
        raise HTTPException(
            503,
            {
                "code": "REVENUE_EVENT_SYNC_DISABLED",
                "message": "Revenue event sync is disabled",
            },
        )
    event_id, created = await LeadRepository(session).create_revenue(
        tenant_id=body.tenant_id,
        lead_id=body.lead_id,
        event_type=body.event_type,
        amount=body.amount,
        currency=body.currency.upper() if body.currency else None,
        source_system=body.source_system,
        external_reference=body.external_reference,
        occurred_at=body.occurred_at,
        is_synthetic=body.is_synthetic,
    )
    if created:
        revenue_events.labels(
            type=body.event_type, currency=(body.currency or "NONE").upper()
        ).inc()
    return {
        "revenue_event_id": event_id,
        "created": created,
        "authoritative_source": body.source_system,
    }


@router.post("/analytics/attribution/revenue/{event_id}/calculate")
async def calculate(
    event_id: UUID,
    body: AttributionRequest,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("attribution.read", permissions)
    if not settings.attribution_engine_enabled:
        raise HTTPException(
            503,
            {
                "code": "ATTRIBUTION_ENGINE_DISABLED",
                "message": "Attribution engine is disabled",
            },
        )
    try:
        result = await LeadRepository(session).calculate_attribution(
            tenant_id=body.tenant_id, revenue_event_id=event_id, model=body.model
        )
        attribution_calculations.labels(model=body.model).inc()
        return result
    except ValueError as exc:
        raise HTTPException(
            404, {"code": str(exc), "message": "Revenue event was not found"}
        ) from exc


@router.get("/ops/leads")
async def list_leads(
    tenant_id: UUID = Query(),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> list[dict]:
    require("ops.leads", permissions)
    rows = (
        (
            await session.execute(
                text(
                    "SELECT id,person_id,company_id,source,status,campaign_id,current_score,next_best_action,consent_status,dnc_status,created_at,updated_at FROM lead_records WHERE tenant_id=:tenant ORDER BY updated_at DESC LIMIT :limit"
                ),
                {"tenant": tenant_id, "limit": limit},
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.post("/analytics/attribution/touches", status_code=201)
async def touch(
    body: TouchCreate,
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("attribution.read", permissions)
    if not settings.attribution_engine_enabled:
        raise HTTPException(
            503,
            {
                "code": "ATTRIBUTION_ENGINE_DISABLED",
                "message": "Attribution engine is disabled",
            },
        )
    touch_id = uuid4()
    utm = {
        "query": build_utm(
            body.network or body.source,
            str(body.campaign_id),
            str(body.content_id or "none"),
        )
    }
    row = (
        await session.execute(
            text(
                "INSERT INTO lead_campaign_touches(id,tenant_id,lead_id,campaign_id,content_id,network,provider,source,utm,event_type,source_event_id,occurred_at) SELECT :id,:tenant,:lead,:campaign,:content,:network,:provider,:source,:utm,:type,:event,:occurred WHERE EXISTS (SELECT 1 FROM lead_records WHERE id=:lead AND tenant_id=:tenant) ON CONFLICT (tenant_id,source,source_event_id) DO NOTHING RETURNING id"
            ),
            {
                "id": touch_id,
                "tenant": body.tenant_id,
                "lead": body.lead_id,
                "campaign": body.campaign_id,
                "content": body.content_id,
                "network": body.network,
                "provider": body.provider,
                "source": body.source,
                "utm": json.dumps(utm),
                "type": body.event_type,
                "event": body.source_event_id,
                "occurred": body.occurred_at,
            },
        )
    ).scalar_one_or_none()
    if row is None:
        existing_touch_id: UUID | None = (
            await session.execute(
                text(
                    "SELECT id FROM lead_campaign_touches WHERE tenant_id=:tenant AND source=:source AND source_event_id=:event"
                ),
                {
                    "tenant": body.tenant_id,
                    "source": body.source,
                    "event": body.source_event_id,
                },
            )
        ).scalar_one_or_none()
        if existing_touch_id is None:
            await session.rollback()
            raise HTTPException(
                404, {"code": "LEAD_NOT_FOUND", "message": "Lead was not found"}
            )
        touch_id = existing_touch_id
    await session.commit()
    return {"touch_id": touch_id, "created": row is not None, "utm": utm}


@router.get("/analytics/attribution/{dimension}")
async def attribution_view(
    dimension: Literal[
        "campaigns", "content", "networks", "providers", "leads", "revenue"
    ],
    tenant_id: UUID = Query(),
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> list[dict]:
    require("attribution.read", permissions)
    if dimension == "revenue":
        rows = (
            (
                await session.execute(
                    text(
                        "SELECT id,lead_id,type,amount,currency,occurred_at,source_system,confidence FROM revenue_events WHERE tenant_id=:tenant ORDER BY occurred_at DESC LIMIT 500"
                    ),
                    {"tenant": tenant_id},
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]
    rows = (
        (
            await session.execute(
                text(ATTRIBUTION_GROUP_QUERIES[dimension]),
                {"tenant": tenant_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


@router.get("/ops/leads/{lead_id}")
async def lead_detail(
    lead_id: UUID,
    tenant_id: UUID = Query(),
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("ops.leads", permissions)
    row = (
        (
            await session.execute(
                text(
                    "SELECT id,person_id,company_id,source,status,campaign_id,current_score,next_best_action,consent_status,dnc_status,jurisdiction,created_at,updated_at FROM lead_records WHERE id=:id AND tenant_id=:tenant"
                ),
                {"id": lead_id, "tenant": tenant_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(
            404, {"code": "LEAD_NOT_FOUND", "message": "Lead was not found"}
        )
    interactions = (
        (
            await session.execute(
                text(
                    "SELECT id,interaction_type,source,source_event_id,campaign_id,content_id,occurred_at FROM lead_interactions WHERE lead_id=:lead AND tenant_id=:tenant ORDER BY occurred_at DESC LIMIT 100"
                ),
                {"lead": lead_id, "tenant": tenant_id},
            )
        )
        .mappings()
        .all()
    )
    return {"lead": dict(row), "timeline": [dict(item) for item in interactions]}


@router.get("/ops/identities/{identity_id}")
async def ops_identity(
    identity_id: UUID,
    tenant_id: UUID = Query(),
    session: AsyncSession = Depends(get_session),
    permissions: str | None = Header(None, alias="X-Codestra-Permissions"),
) -> dict:
    require("ops.leads", permissions)
    person_value = await LeadRepository(session).get_person(tenant_id, identity_id)
    company_value = await LeadRepository(session).get_company(tenant_id, identity_id)
    if not person_value and not company_value:
        raise HTTPException(
            404, {"code": "IDENTITY_NOT_FOUND", "message": "Identity was not found"}
        )
    return {
        "type": "PERSON" if person_value else "COMPANY",
        "identity": person_value or company_value,
    }
