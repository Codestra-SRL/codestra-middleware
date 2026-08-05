"""Fail-closed legal intake, matter, and confidentiality policy contracts."""
from dataclasses import dataclass

INTAKE_STATES = frozenset({"DRAFT", "SUBMITTED", "IDENTITY_PENDING", "CONFLICT_CHECK_PENDING", "CONFLICT_REVIEW", "CONSULTATION_PENDING", "CONSULTATION_SCHEDULED", "CONSULTATION_COMPLETED", "ATTORNEY_REVIEW", "MORE_INFORMATION_REQUIRED", "ENGAGEMENT_PENDING", "ENGAGED", "DECLINED", "REFERRED", "WITHDRAWN", "EXPIRED", "CANCELLED", "ERROR", "RECONCILIATION_REQUIRED"})
MATTER_STATES = frozenset({"DRAFT", "OPENING_REVIEW", "CONFLICT_PENDING", "ENGAGEMENT_PENDING", "OPEN", "ON_HOLD", "CLOSING", "CLOSED", "REOPENED", "DECLINED", "REFERRED", "ARCHIVED"})
CONFLICT_OUTCOMES = frozenset({"CLEAR_FOR_REVIEW", "POTENTIAL_CONFLICT", "CONFLICT_CONFIRMED", "WAIVER_REQUIRED", "INSUFFICIENT_INFORMATION", "ESCALATED", "CLOSED"})


class LegalPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class MatterOpeningAuthorization:
    tenant_id: str
    matter_id: str
    authorized_role: bool
    conflict_review_complete: bool
    engagement_satisfied: bool
    owner_assigned: bool
    confidentiality_controls_present: bool


@dataclass(frozen=True)
class EthicalWallDecision:
    tenant_id: str
    matter_id: str
    user_id: str
    member_of_wall: bool
    privileged_override: bool = False
    override_reason: str = ""


def authorize_matter_opening(request: MatterOpeningAuthorization) -> bool:
    return bool(request.tenant_id and request.matter_id and request.authorized_role and request.conflict_review_complete and request.engagement_satisfied and request.owner_assigned and request.confidentiality_controls_present)


def allow_matter_access(decision: EthicalWallDecision) -> bool:
    if not decision.tenant_id or not decision.matter_id or not decision.user_id:
        return False
    if decision.member_of_wall:
        return False
    return decision.privileged_override and bool(decision.override_reason.strip())


def validate_intake_state(state: str) -> str:
    if state not in INTAKE_STATES:
        raise LegalPolicyError("intake state requires approved value")
    return state


def validate_conflict_outcome(outcome: str) -> str:
    if outcome not in CONFLICT_OUTCOMES:
        raise LegalPolicyError("conflict outcome requires approved value")
    return outcome
