"""Fail-closed evaluation, learning, and promotion contracts."""
from dataclasses import dataclass

PROMOTION_STATES = frozenset({"CAPTURED", "CLASSIFIED", "VALIDATED", "REVIEWED", "APPROVED_FOR_TEST", "TESTING", "PASSED", "FAILED", "READY_FOR_STAGING", "STAGING", "OBSERVING", "APPROVED", "REJECTED", "ROLLED_BACK"})
PERFORMANCE_STATES = frozenset({"UNASSESSED", "MEETS_EXPECTATIONS", "NEEDS_REVIEW", "COACHING_REQUIRED", "RESTRICTED", "SUSPENSION_RECOMMENDED", "SUSPENDED", "RECOVERY_OBSERVATION", "RETIRED"})


@dataclass(frozen=True)
class PromotionRequest:
    employee_id: str
    proposal_id: str
    reviewer_id: str
    baseline_passed: bool
    candidate_passed: bool
    security_passed: bool
    isolation_passed: bool
    rollback_configured: bool
    self_requested: bool = False
    self_approved: bool = False


def authorize_promotion(request: PromotionRequest) -> tuple[bool, str]:
    if not request.employee_id or not request.proposal_id or not request.reviewer_id:
        return False, "MISSING_CONTEXT"
    if request.self_requested or request.self_approved or request.employee_id == request.reviewer_id:
        return False, "SELF_PROMOTION"
    if not all((request.baseline_passed, request.candidate_passed, request.security_passed, request.isolation_passed, request.rollback_configured)):
        return False, "GATE_FAILED"
    return True, "VALID"


def score_is_evidence_backed(*, evidence_count: int, confidence: float, threshold: float, human_reviewed: bool = False) -> bool:
    return bool(evidence_count > 0 and 0 <= confidence <= 1 and threshold >= 0 and confidence >= threshold and human_reviewed)


def authorize_feedback_mutation(*, actor_is_reviewer: bool, deletes_history: bool, employee_self_action: bool) -> bool:
    return bool(actor_is_reviewer and not deletes_history and not employee_self_action)
