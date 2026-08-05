"""Fail-closed prompt, model, dataset and evaluation governance contracts."""
from dataclasses import dataclass

PROMOTION_STATES = frozenset({"DRAFT", "VALIDATING", "REVIEW_REQUIRED", "APPROVED", "PROMOTED", "REJECTED", "ROLLED_BACK"})


class GovernanceError(ValueError):
    pass


@dataclass(frozen=True)
class EvaluationGate:
    schema_pass_rate: float
    unsupported_claims: int
    critical_compliance_findings: int
    human_review_complete: bool


def evaluate_gate(gate: EvaluationGate, minimum_schema_rate: float = 0.98) -> str:
    if gate.schema_pass_rate < minimum_schema_rate or gate.unsupported_claims or gate.critical_compliance_findings:
        return "REJECTED"
    if not gate.human_review_complete:
        return "REVIEW_REQUIRED"
    return "APPROVED"


def validate_promotion(state: str, gate_outcome: str, production_enabled: bool) -> str:
    if state != "APPROVED" or gate_outcome != "APPROVED" or production_enabled:
        raise GovernanceError("promotion blocked by governance gate")
    return "PROMOTED"
