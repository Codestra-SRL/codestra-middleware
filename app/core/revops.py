"""Fail-closed sales, marketing, and revenue-operations policy contracts."""
from dataclasses import dataclass

OPPORTUNITY_STATES = frozenset({"NEW", "QUALIFIED", "DISCOVERY", "PROPOSAL", "NEGOTIATION", "WON", "LOST", "ON_HOLD", "CLOSED"})
CAMPAIGN_STATES = frozenset({"DRAFT", "PLANNED", "IN_REVIEW", "APPROVED", "PAUSED", "COMPLETED", "CANCELLED"})
COMMISSION_STATES = frozenset({"DRAFT", "PENDING_REVIEW", "APPROVED", "PAID", "VOIDED", "RECOVERED"})


class RevOpsPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class ForecastObservation:
    tenant_id: str
    opportunity_id: str
    score: float
    advisory: bool = True


@dataclass(frozen=True)
class CommissionApproval:
    tenant_id: str
    opportunity_id: str
    amount_minor: int
    human_approved: bool
    pricing_approved: bool


def validate_opportunity_state(state: str) -> str:
    if state not in OPPORTUNITY_STATES:
        raise RevOpsPolicyError("opportunity state requires approved value")
    return state


def validate_campaign_state(state: str) -> str:
    if state not in CAMPAIGN_STATES:
        raise RevOpsPolicyError("campaign state requires approved value")
    return state


def authorize_commission(approval: CommissionApproval) -> bool:
    return bool(approval.tenant_id and approval.opportunity_id and approval.amount_minor >= 0 and approval.human_approved and approval.pricing_approved)


def normalize_advisory_score(observation: ForecastObservation) -> float:
    if not observation.tenant_id or not observation.opportunity_id or not observation.advisory:
        raise RevOpsPolicyError("forecast observations must remain tenant-scoped and advisory")
    if not 0 <= observation.score <= 1:
        raise RevOpsPolicyError("forecast score must be between zero and one")
    return observation.score
