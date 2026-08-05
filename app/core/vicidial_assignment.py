"""Fail-closed eligibility and assignment state primitives."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

STATES = frozenset({"ELIGIBILITY_PENDING", "ELIGIBLE", "INELIGIBLE", "REVIEW_REQUIRED", "APPROVED_FOR_ASSIGNMENT", "ASSIGNMENT_REQUESTED", "ASSIGNMENT_QUEUED", "ASSIGNING", "ASSIGNED", "ASSIGNMENT_RETRY_SCHEDULED", "ASSIGNMENT_FAILED", "ASSIGNMENT_UNKNOWN", "DUPLICATE_BLOCKED", "CANCELLED"})
TRANSITIONS = {
    "ELIGIBILITY_PENDING": {"ELIGIBLE", "INELIGIBLE", "REVIEW_REQUIRED"},
    "ELIGIBLE": {"APPROVED_FOR_ASSIGNMENT"},
    "APPROVED_FOR_ASSIGNMENT": {"ASSIGNMENT_REQUESTED", "CANCELLED"},
    "ASSIGNMENT_REQUESTED": {"ASSIGNMENT_QUEUED", "CANCELLED"},
    "ASSIGNMENT_QUEUED": {"ASSIGNING"},
    "ASSIGNING": {"ASSIGNED", "ASSIGNMENT_RETRY_SCHEDULED", "ASSIGNMENT_FAILED", "ASSIGNMENT_UNKNOWN", "DUPLICATE_BLOCKED"},
    "ASSIGNMENT_RETRY_SCHEDULED": {"ASSIGNMENT_QUEUED"},
    "ASSIGNMENT_UNKNOWN": {"ASSIGNED", "ASSIGNMENT_FAILED", "ASSIGNMENT_RETRY_SCHEDULED"},
}


class AssignmentPolicyError(ValueError):
    pass


def transition(current: str, target: str) -> str:
    if current not in STATES or target not in STATES or target not in TRANSITIONS.get(current, set()):
        raise AssignmentPolicyError(f"invalid assignment transition {current}->{target}")
    return target


def external_key(tenant_id: str, lead_record_id: str) -> str:
    if not tenant_id or not lead_record_id:
        raise AssignmentPolicyError("tenant and lead identifiers are required")
    return f"codestra:{tenant_id}:vicidial-lead:{lead_record_id}"


@dataclass(frozen=True)
class AssignmentPolicy:
    allowed_campaigns: tuple[str, ...] = ("STAGING_CAMPAIGN",)
    allowed_lists: tuple[str, ...] = ("STAGING_LEADS",)
    maximum_batch_size: int = 5
    require_human_approval: bool = True
    require_valid_phone: bool = True
    minimum_phone_confidence: float = 0.60
    block_confirmed_duplicates: bool = True
    block_suppressed_numbers: bool = True
    allow_active_campaign_assignment: bool = False
    allow_live_dialing: bool = False


def eligibility_errors(lead: dict[str, Any], policy: AssignmentPolicy, *, target_campaign: str, target_list: str) -> list[str]:
    errors: list[str] = []
    if not lead.get("approved_for_import"):
        errors.append("human_approval_required")
    if not lead.get("odoo_lead_id"):
        errors.append("odoo_record_required")
    if not lead.get("external_key"):
        errors.append("external_key_required")
    phone = str(lead.get("normalized_phone") or lead.get("phone") or "")
    if policy.require_valid_phone and (not re.fullmatch(r"\+?[1-9][0-9]{7,14}", re.sub(r"[ ()-]", "", phone))):
        errors.append("invalid_phone")
    if float(lead.get("phone_confidence") or 0) < policy.minimum_phone_confidence:
        errors.append("phone_confidence_below_policy")
    if policy.block_confirmed_duplicates and lead.get("duplicate_status") == "CONFIRMED_DUPLICATE":
        errors.append("duplicate_blocked")
    if policy.block_suppressed_numbers and lead.get("suppressed"):
        errors.append("suppression_blocked")
    if target_campaign not in policy.allowed_campaigns:
        errors.append("campaign_not_allowed")
    if target_list not in policy.allowed_lists:
        errors.append("list_not_allowed")
    if policy.allow_active_campaign_assignment:
        errors.append("active_campaign_assignment_forbidden")
    if policy.allow_live_dialing:
        errors.append("live_dialing_forbidden")
    return errors


def request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

