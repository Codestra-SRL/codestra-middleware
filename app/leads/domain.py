from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from urllib.parse import urlencode
from urllib.parse import urlsplit


class MatchConfidence(str, Enum):
    EXACT = "EXACT"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class NextAction(str, Enum):
    CALL_NOW = "CALL_NOW"
    CALL_LATER = "CALL_LATER"
    EMAIL = "EMAIL"
    SOCIAL_REPLY = "SOCIAL_REPLY"
    BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
    NURTURE = "NURTURE"
    REQUEST_INFORMATION = "REQUEST_INFORMATION"
    SUPPORT_HANDOFF = "SUPPORT_HANDOFF"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    DO_NOT_CONTACT = "DO_NOT_CONTACT"
    CLOSE_LOST = "CLOSE_LOST"
    NO_ACTION = "NO_ACTION"


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).strip().split())


def normalize_email(value: str) -> str:
    normalized = normalize_text(value).casefold()
    if len(normalized) > 320 or not EMAIL_RE.fullmatch(normalized):
        raise ValueError("LEAD_EMAIL_INVALID")
    return normalized


def normalize_domain(value: str) -> str:
    candidate = value if "://" in value else f"https://{value}"
    parsed = urlsplit(candidate)
    if parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("LEAD_DOMAIN_INVALID")
    try:
        host = parsed.hostname.encode("idna").decode("ascii").casefold().rstrip(".")
    except UnicodeError as exc:
        raise ValueError("LEAD_DOMAIN_INVALID") from exc
    if host.startswith("www."):
        host = host[4:]
    if "." not in host or len(host) > 253:
        raise ValueError("LEAD_DOMAIN_INVALID")
    return host


def normalize_phone(
    value: str, country_hint: str | None = None
) -> tuple[str | None, str]:
    raw = normalize_text(value)
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") and 8 <= len(digits) <= 15:
        return f"+{digits}", "NORMALIZED"
    country_codes = {
        "US": "1",
        "CA": "1",
        "DO": "1",
        "GB": "44",
        "FR": "33",
        "ES": "34",
        "HT": "509",
    }
    code = country_codes.get((country_hint or "").upper())
    if code and 7 <= len(digits) <= 14:
        if code == "1" and len(digits) == 10:
            return f"+1{digits}", "NORMALIZED"
        if digits.startswith(code):
            return f"+{digits}", "NORMALIZED"
        return f"+{code}{digits}", "NORMALIZED"
    return None, "AMBIGUOUS"


def stable_hash(*values: str | None) -> str:
    canonical = "\x1f".join(value or "" for value in values)
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class MatchResult:
    confidence: MatchConfidence
    score: int
    auto_link: bool
    signals: dict[str, int]
    conflict: bool = False


def match_identity(candidate: dict[str, Any], existing: dict[str, Any]) -> MatchResult:
    signals: dict[str, int] = {}
    exact_fields = (
        ("social_profile_id", 100),
        ("email", 95),
        ("phone", 95),
        ("external_id", 100),
    )
    conflicts = False
    for field, weight in exact_fields:
        left, right = candidate.get(field), existing.get(field)
        if left and right:
            if left == right:
                signals[field] = weight
            elif field in {"email", "phone", "social_profile_id"}:
                conflicts = True
    if any(weight >= 95 for weight in signals.values()) and not conflicts:
        return MatchResult(MatchConfidence.EXACT, 100, True, signals)
    if candidate.get("name") and candidate.get("name") == existing.get("name"):
        signals["name"] = 30
    if candidate.get("company_domain") and candidate.get(
        "company_domain"
    ) == existing.get("company_domain"):
        signals["company_domain"] = 40
    if candidate.get("country") and candidate.get("country") == existing.get("country"):
        signals["country"] = 10
    score = min(100, sum(signals.values()))
    confidence = (
        MatchConfidence.HIGH
        if score >= 75
        else MatchConfidence.MEDIUM
        if score >= 50
        else MatchConfidence.LOW
        if score
        else MatchConfidence.UNKNOWN
    )
    return MatchResult(confidence, score, False, signals, conflicts)


@dataclass(frozen=True)
class ActionDecision:
    action: NextAction
    reasons: tuple[str, ...]
    eligible_for_contact: bool


def next_best_action(
    *,
    dnc: str,
    consent: str,
    intent: str,
    score: int,
    phone: bool,
    email: bool,
    social: bool,
) -> ActionDecision:
    if dnc not in {"CLEAR", "UNKNOWN"}:
        return ActionDecision(NextAction.DO_NOT_CONTACT, ("DNC_BLOCK",), False)
    if consent != "GRANTED":
        return ActionDecision(NextAction.MANUAL_REVIEW, ("CONSENT_NOT_GRANTED",), False)
    if intent == "SUPPORT":
        return ActionDecision(NextAction.SUPPORT_HANDOFF, ("SUPPORT_INTENT",), True)
    if intent == "BUYING_INTENT" and score >= 70 and phone:
        return ActionDecision(
            NextAction.CALL_NOW, ("HIGH_BUYING_INTENT", "VALID_PHONE"), True
        )
    if intent == "BUYING_INTENT" and email:
        return ActionDecision(NextAction.EMAIL, ("BUYING_INTENT", "VALID_EMAIL"), True)
    if social:
        return ActionDecision(
            NextAction.SOCIAL_REPLY, ("SOCIAL_CHANNEL_AVAILABLE",), True
        )
    return ActionDecision(NextAction.NURTURE, ("LOW_CONTACT_READINESS",), True)


def quality_score(signals: dict[str, int]) -> tuple[int, dict[str, int]]:
    ceilings = {
        "intent_quality": 25,
        "contactability": 15,
        "identity_confidence": 15,
        "company_fit": 15,
        "campaign_fit": 10,
        "engagement": 10,
        "urgency": 5,
        "source_quality": 5,
    }
    components = {
        key: max(0, min(ceilings[key], int(signals.get(key, 0)))) for key in ceilings
    }
    return sum(components.values()), components


def build_utm(source: str, campaign: str, content: str) -> str:
    return urlencode(
        {
            "utm_source": source.casefold(),
            "utm_medium": "social",
            "utm_campaign": campaign,
            "utm_content": content,
        }
    )


def attribution_weights(
    model: str,
    touches: list[datetime],
    occurred_at: datetime,
    *,
    first_weight: Decimal = Decimal("0.4"),
    last_weight: Decimal = Decimal("0.4"),
    half_life_days: int = 7,
) -> list[Decimal]:
    if not touches:
        return []
    count = len(touches)
    if model == "FIRST_TOUCH":
        return [Decimal(1) if i == 0 else Decimal(0) for i in range(count)]
    if model == "LAST_TOUCH":
        return [Decimal(1) if i == count - 1 else Decimal(0) for i in range(count)]
    if model == "LINEAR":
        raw = [Decimal(1) / Decimal(count)] * count
    elif model == "POSITION_BASED":
        if count == 1:
            return [Decimal(1)]
        if count == 2:
            return [Decimal("0.5"), Decimal("0.5")]
        middle = (Decimal(1) - first_weight - last_weight) / Decimal(count - 2)
        raw = [first_weight] + [middle] * (count - 2) + [last_weight]
    elif model == "TIME_DECAY":
        raw = [
            Decimal(
                str(
                    math.pow(
                        0.5,
                        max(
                            0.0,
                            (occurred_at - touch).total_seconds()
                            / 86400
                            / half_life_days,
                        ),
                    )
                )
            )
            for touch in touches
        ]
    else:
        raise ValueError("ATTRIBUTION_MODEL_UNSUPPORTED")
    total = sum(raw)
    weights = [value / total for value in raw]
    weights[-1] += Decimal(1) - sum(weights)
    return weights
