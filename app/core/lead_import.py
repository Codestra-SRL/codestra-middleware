"""Fail-closed review and controlled Odoo-import policy primitives."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

REVIEW_STATES = frozenset(
    {
        "DISCOVERED", "NORMALIZED", "VERIFICATION_PENDING", "VERIFICATION_COMPLETE",
        "REVIEW_REQUIRED", "UNDER_REVIEW", "APPROVED_FOR_IMPORT", "REJECTED",
        "POSSIBLE_DUPLICATE", "CONFIRMED_DUPLICATE", "IMPORT_REQUESTED", "IMPORT_QUEUED",
        "IMPORTING", "IMPORTED", "IMPORT_RETRY_SCHEDULED", "IMPORT_FAILED", "IMPORT_UNKNOWN",
        "CANCELLED",
    }
)
TRANSITIONS = {
    "REVIEW_REQUIRED": {"UNDER_REVIEW"},
    "UNDER_REVIEW": {"APPROVED_FOR_IMPORT", "REJECTED", "POSSIBLE_DUPLICATE"},
    "POSSIBLE_DUPLICATE": {"UNDER_REVIEW", "CONFIRMED_DUPLICATE", "APPROVED_FOR_IMPORT"},
    "APPROVED_FOR_IMPORT": {"IMPORT_REQUESTED", "CANCELLED"},
    "IMPORT_REQUESTED": {"IMPORT_QUEUED", "CANCELLED"},
    "IMPORT_QUEUED": {"IMPORTING"},
    "IMPORTING": {"IMPORTED", "IMPORT_RETRY_SCHEDULED", "IMPORT_FAILED", "IMPORT_UNKNOWN"},
    "IMPORT_RETRY_SCHEDULED": {"IMPORT_QUEUED"},
    "IMPORT_UNKNOWN": {"IMPORTED", "IMPORT_FAILED", "IMPORT_RETRY_SCHEDULED"},
}
REVIEW_ROLES = frozenset({"LEAD_REVIEWER", "LEAD_REVIEW_MANAGER"})
IMPORT_ROLES = frozenset({"LEAD_IMPORT_OPERATOR", "LEAD_IMPORT_APPROVER"})


class LeadImportPolicyError(ValueError):
    pass


def transition(current: str, target: str) -> str:
    if current not in REVIEW_STATES or target not in REVIEW_STATES:
        raise LeadImportPolicyError("unknown lead review state")
    if target not in TRANSITIONS.get(current, set()):
        raise LeadImportPolicyError(f"invalid transition {current}->{target}")
    return target


def external_key(tenant_id: str, lead_record_id: str) -> str:
    if not tenant_id or not lead_record_id:
        raise LeadImportPolicyError("tenant and lead identifiers are required")
    return f"codestra:{tenant_id}:lead:{lead_record_id}"


@dataclass(frozen=True)
class ApprovalPolicy:
    minimum_lead_score: float = 60
    minimum_contact_confidence: float = 0.60
    require_phone: bool = True
    require_verified_phone: bool = False
    require_email: bool = False
    require_source_evidence: bool = True
    block_confirmed_duplicates: bool = True
    require_reviewer_note: bool = False


def approval_errors(lead: dict[str, Any], policy: ApprovalPolicy) -> list[str]:
    errors: list[str] = []
    if not lead.get("company_name"):
        errors.append("company_name_required")
    if policy.require_source_evidence and not lead.get("source_history"):
        errors.append("source_evidence_required")
    if policy.require_phone and not (lead.get("normalized_phone") or lead.get("phone")):
        errors.append("phone_required")
    if policy.require_verified_phone and lead.get("verification_status") != "VERIFIED":
        errors.append("verified_phone_required")
    if policy.require_email and not (lead.get("normalized_email") or lead.get("email")):
        errors.append("email_required")
    if float(lead.get("lead_score") or 0) < policy.minimum_lead_score:
        errors.append("minimum_lead_score_not_met")
    if float(lead.get("ownership_confidence") or 0) > 0 and lead.get("ownership_status") == "CONFIRMED_OWNER":
        errors.append("unsupported_ownership_claim")
    if policy.block_confirmed_duplicates and lead.get("duplicate_status") == "CONFIRMED_DUPLICATE":
        errors.append("confirmed_duplicate")
    return errors


def request_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

