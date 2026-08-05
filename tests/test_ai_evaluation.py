from app.core.ai_evaluation import (
    PERFORMANCE_STATES,
    PROMOTION_STATES,
    PromotionRequest,
    authorize_feedback_mutation,
    authorize_promotion,
    score_is_evidence_backed,
)


def test_states_and_evidence_requirements():
    assert {"CAPTURED", "TESTING", "STAGING", "ROLLED_BACK"}.issubset(PROMOTION_STATES)
    assert {"UNASSESSED", "COACHING_REQUIRED", "SUSPENDED"}.issubset(PERFORMANCE_STATES)
    assert score_is_evidence_backed(evidence_count=2, confidence=0.9, threshold=0.8, human_reviewed=True)
    assert not score_is_evidence_backed(evidence_count=0, confidence=0.9, threshold=0.8, human_reviewed=True)
    assert not score_is_evidence_backed(evidence_count=2, confidence=0.9, threshold=0.8, human_reviewed=False)


def test_promotion_requires_baseline_candidate_security_isolation_and_rollback():
    base = dict(employee_id="e1", proposal_id="p1", reviewer_id="human-1", baseline_passed=True, candidate_passed=True, security_passed=True, isolation_passed=True, rollback_configured=True)
    assert authorize_promotion(PromotionRequest(**base)) == (True, "VALID")
    assert authorize_promotion(PromotionRequest(**{**base, "security_passed": False}))[1] == "GATE_FAILED"
    assert authorize_promotion(PromotionRequest(**{**base, "employee_id": "human-1"}))[1] == "SELF_PROMOTION"
    assert authorize_promotion(PromotionRequest(**{**base, "self_requested": True}))[1] == "SELF_PROMOTION"


def test_feedback_cannot_delete_history_or_be_self_authored():
    assert authorize_feedback_mutation(actor_is_reviewer=True, deletes_history=False, employee_self_action=False)
    assert not authorize_feedback_mutation(actor_is_reviewer=False, deletes_history=False, employee_self_action=False)
    assert not authorize_feedback_mutation(actor_is_reviewer=True, deletes_history=True, employee_self_action=False)
    assert not authorize_feedback_mutation(actor_is_reviewer=True, deletes_history=False, employee_self_action=True)
