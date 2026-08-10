from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import urlsplit


class CampaignState(str, Enum):
    DRAFT = "DRAFT"
    CONTENT_GENERATING = "CONTENT_GENERATING"
    CONTENT_REVIEW = "CONTENT_REVIEW"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


CAMPAIGN_TRANSITIONS: dict[CampaignState, frozenset[CampaignState]] = {
    CampaignState.DRAFT: frozenset(
        {CampaignState.CONTENT_GENERATING, CampaignState.CANCELLED}
    ),
    CampaignState.CONTENT_GENERATING: frozenset(
        {CampaignState.CONTENT_REVIEW, CampaignState.FAILED}
    ),
    CampaignState.CONTENT_REVIEW: frozenset(
        {CampaignState.APPROVAL_REQUIRED, CampaignState.DRAFT}
    ),
    CampaignState.APPROVAL_REQUIRED: frozenset(
        {CampaignState.APPROVED, CampaignState.DRAFT}
    ),
    CampaignState.APPROVED: frozenset(
        {CampaignState.SCHEDULED, CampaignState.CANCELLED}
    ),
    CampaignState.SCHEDULED: frozenset({CampaignState.ACTIVE, CampaignState.CANCELLED}),
    CampaignState.ACTIVE: frozenset(
        {CampaignState.PAUSED, CampaignState.COMPLETED, CampaignState.FAILED}
    ),
    CampaignState.PAUSED: frozenset({CampaignState.ACTIVE, CampaignState.CANCELLED}),
    CampaignState.COMPLETED: frozenset(),
    CampaignState.FAILED: frozenset({CampaignState.DRAFT, CampaignState.CANCELLED}),
    CampaignState.CANCELLED: frozenset(),
}


class InvalidCampaignTransition(ValueError):
    pass


def require_transition(old: CampaignState, new: CampaignState) -> None:
    if new not in CAMPAIGN_TRANSITIONS[old]:
        raise InvalidCampaignTransition(f"{old.value} cannot transition to {new.value}")


class LeadCategory(str, Enum):
    HOT_LEAD = "HOT_LEAD"
    WARM_LEAD = "WARM_LEAD"
    COLD_LEAD = "COLD_LEAD"
    SUPPORT = "SUPPORT"
    GENERAL = "GENERAL"
    COMPLAINT = "COMPLAINT"
    SPAM = "SPAM"
    NOT_A_LEAD = "NOT_A_LEAD"


@dataclass(frozen=True)
class LeadScore:
    score: int
    category: LeadCategory
    factors: dict[str, int]


def score_lead(signals: dict[str, bool]) -> LeadScore:
    weights = {
        "buying_intent": 35,
        "company_match": 15,
        "contact_available": 15,
        "location_match": 10,
        "engaged": 10,
        "urgent": 10,
        "campaign_fit": 5,
    }
    factors = {
        name: weight for name, weight in weights.items() if signals.get(name, False)
    }
    score = min(100, sum(factors.values()))
    category = (
        LeadCategory.HOT_LEAD
        if score >= 70
        else LeadCategory.WARM_LEAD
        if score >= 40
        else LeadCategory.COLD_LEAD
    )
    return LeadScore(score, category, factors)


def lead_identity_hash(
    *, email: str | None, phone: str | None, profile: str | None
) -> str | None:
    values = [
        unicodedata.normalize("NFKC", value).strip().casefold()
        for value in (email, phone, profile)
        if value
    ]
    return hashlib.sha256("\x1f".join(values).encode()).hexdigest() if values else None


ANALYTICS_METRICS = frozenset(
    {
        "impressions",
        "reach",
        "views",
        "likes",
        "reactions",
        "comments",
        "shares",
        "clicks",
        "engagements",
        "video_views",
        "watch_time_seconds",
        "followers_delta",
        "conversion_count",
        "lead_count",
        "qualified_lead_count",
    }
)


def normalize_analytics(values: dict[str, Any]) -> dict[str, float | int | None]:
    normalized: dict[str, float | int | None] = {}
    for name in ANALYTICS_METRICS:
        value = values.get(name)
        normalized[name] = (
            value
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else None
        )
    return normalized


@dataclass(frozen=True)
class ProviderHealthScore:
    score: int
    status: str
    components: dict[str, int]


def provider_health_score(
    *,
    reachable: bool,
    authenticated: bool,
    latency_ms: float,
    error_rate: float,
    poll_lag_seconds: int,
) -> ProviderHealthScore:
    components = {
        "api": 35 if reachable else 0,
        "auth": 25 if authenticated else 0,
        "latency": 15 if latency_ms <= 500 else 8 if latency_ms <= 2000 else 0,
        "errors": 15 if error_rate <= 0.01 else 8 if error_rate <= 0.1 else 0,
        "polling": 10
        if poll_lag_seconds <= 300
        else 5
        if poll_lag_seconds <= 900
        else 0,
    }
    score = sum(components.values())
    status = (
        "AUTH_REQUIRED"
        if not authenticated
        else "UNAVAILABLE"
        if not reachable
        else "HEALTHY"
        if score >= 80
        else "DEGRADED"
    )
    return ProviderHealthScore(score, status, components)


SAFE_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"}
)


def validate_media(
    *, content_type: str, filename: str, size: int, checksum: str, maximum_bytes: int
) -> None:
    if (
        content_type not in SAFE_MEDIA_TYPES
        or mimetypes.guess_type(filename)[0] != content_type
    ):
        raise ValueError("SOCIAL_MEDIA_TYPE_UNSUPPORTED")
    if size <= 0 or size > maximum_bytes:
        raise ValueError("SOCIAL_MEDIA_SIZE_INVALID")
    if len(checksum) != 64 or any(
        ch not in "0123456789abcdef" for ch in checksum.casefold()
    ):
        raise ValueError("SOCIAL_MEDIA_CHECKSUM_INVALID")


def safe_location_reference(reference: str) -> str:
    parsed = urlsplit(reference)
    if parsed.scheme not in {"https", "media"} or parsed.username or parsed.password:
        raise ValueError("SOCIAL_MEDIA_LOCATION_INVALID")
    if parsed.scheme == "https":
        addresses = []
        try:
            addresses.append(ipaddress.ip_address(parsed.hostname or ""))
        except ValueError:
            pass
        if any(not address.is_global for address in addresses):
            raise ValueError("SOCIAL_MEDIA_LOCATION_INVALID")
    return reference
