"""Fail-closed campaign activation and one-call canary gates."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime


class CanaryGateError(ValueError):
    pass


@dataclass(frozen=True)
class CanaryAuthorization:
    campaign_id: str
    list_id: str
    maintenance_start: datetime
    maintenance_end: datetime
    authorization_reference: str
    approved_by: str
    max_leads: int = 1
    max_calls: int = 1


def normalize_phone(phone: str) -> str:
    normalized = re.sub(r"[^0-9+]", "", phone or "")
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", normalized):
        raise CanaryGateError("approved test number is invalid")
    return normalized


def phone_hash(phone: str) -> str:
    return hashlib.sha256(normalize_phone(phone).encode()).hexdigest()


def enforce_window(now: datetime, *, start: datetime, end: datetime) -> None:
    current = now if now.tzinfo else now.replace(tzinfo=UTC)
    if not (start <= current <= end):
        raise CanaryGateError("outside approved maintenance window")


def enforce_limits(*, call_count: int, lead_count: int, max_calls: int = 1, max_leads: int = 1) -> None:
    if lead_count >= max_leads:
        raise CanaryGateError("one-lead canary limit reached")
    if call_count >= max_calls:
        raise CanaryGateError("one-call canary limit reached")


def enforce_campaign_safety(*, campaign_id: str, list_id: str, active: bool, hopper_count: int, dialing_enabled: bool, authorization: CanaryAuthorization) -> None:
    if campaign_id != authorization.campaign_id or list_id != authorization.list_id:
        raise CanaryGateError("campaign or list is outside the approved canary")
    if active and dialing_enabled:
        raise CanaryGateError("live dialing must remain disabled before controlled activation")
    if hopper_count != 0:
        raise CanaryGateError("hopper must be empty")


def validate_authorization(auth: CanaryAuthorization) -> None:
    if not auth.authorization_reference or not auth.approved_by:
        raise CanaryGateError("written authorization reference and approver are required")
    if auth.max_leads != 1 or auth.max_calls != 1:
        raise CanaryGateError("canary limits must be exactly one lead and one call")
    if auth.maintenance_end <= auth.maintenance_start:
        raise CanaryGateError("maintenance window is invalid")
