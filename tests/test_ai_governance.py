import pytest
from fastapi import HTTPException

from app.api.v1.ai_governance import require_governance
from app.core.ai_governance import EvaluationGate, GovernanceError, evaluate_gate, validate_promotion


def test_evaluation_gate_requires_quality_and_human_review():
    assert evaluate_gate(EvaluationGate(0.99, 0, 0, False)) == "REVIEW_REQUIRED"
    assert evaluate_gate(EvaluationGate(0.97, 0, 0, True)) == "REJECTED"
    assert evaluate_gate(EvaluationGate(0.99, 0, 0, True)) == "APPROVED"


def test_production_promotion_is_fail_closed():
    with pytest.raises(GovernanceError):
        validate_promotion("APPROVED", "APPROVED", True)


def test_governance_role_guard():
    with pytest.raises(HTTPException) as exc:
        require_governance("CUSTOMER_READ_ONLY")
    assert exc.value.status_code == 403
