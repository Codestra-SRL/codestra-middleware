"""Fail-closed campaign, schedule, suppression, and consent contracts."""

from dataclasses import dataclass
from datetime import datetime, time

CAMPAIGN_STATES = frozenset({"DRAFT", "CONFIGURING", "VALIDATING", "READY_FOR_REVIEW", "APPROVED_FOR_STAGING", "STAGING_ACTIVE", "PAUSED", "SUSPENDED", "STOPPED", "RETIRED", "ERROR"})


@dataclass(frozen=True)
class CallingWindow:
    timezone: str
    start: time
    end: time
    allowed_days: frozenset[int]


@dataclass(frozen=True)
class LeadEligibility:
    tenant_id: str
    workspace_id: str
    campaign_id: str
    normalized_phone: str
    consent_state: str
    suppressed: bool
    expires_at: datetime | None = None


def calling_allowed(*, now: datetime, window: CallingWindow, holiday: bool = False) -> bool:
    return now.weekday() in window.allowed_days and not holiday and window.start <= now.timetz().replace(tzinfo=None) <= window.end


def lead_is_eligible(lead: LeadEligibility, *, now: datetime) -> bool:
    return bool(lead.tenant_id and lead.workspace_id and lead.campaign_id and lead.normalized_phone and lead.consent_state in {"GRANTED", "NOT_REQUIRED"} and not lead.suppressed and (lead.expires_at is None or lead.expires_at > now))


def attempt_allowed(*, attempts_today: int, total_attempts: int, max_per_day: int, max_total: int, last_attempt_at: datetime | None, now: datetime, retry_interval_seconds: int) -> bool:
    if attempts_today >= max_per_day or total_attempts >= max_total:
        return False
    return last_attempt_at is None or (now - last_attempt_at).total_seconds() >= retry_interval_seconds
