"""Fail-closed named-customer pilot controls."""
from dataclasses import dataclass

PILOT_PHASES = ("PHASE_0_PREPARATION", "PHASE_1_INTERNAL_CERTIFICATION", "PHASE_2_CUSTOMER_CONFIGURATION", "PHASE_3_CUSTOMER_ACCEPTANCE_TESTING", "PHASE_4_LIMITED_PILOT_ACTIVATION", "PHASE_5_30_DAY_OBSERVATION", "PHASE_6_EXIT_REVIEW", "PHASE_7_EXPAND_REMEDIATE_OR_TERMINATE")
DAILY_STATES = frozenset({"HEALTHY", "HEALTHY_WITH_WARNINGS", "AT_RISK", "CRITICAL", "PAUSED", "SUSPENDED", "NO_DATA"})


@dataclass(frozen=True)
class CustomerPilotPreconditions:
    customer_tenant_id: str
    workspace_ids: tuple[str, ...]
    business_owner: str
    pilot_owner: str
    signed_authorization: bool
    approved_start: str
    approved_end: str
    approved_employees: tuple[str, ...]
    approved_tools: tuple[str, ...]
    approved_budget: bool


def evidence_complete(p: CustomerPilotPreconditions) -> bool:
    return bool(p.customer_tenant_id and p.workspace_ids and p.business_owner and p.pilot_owner and p.signed_authorization and p.approved_start and p.approved_end and p.approved_employees and p.approved_tools and p.approved_budget)


def activation_allowed(*, evidence_complete_flag: bool, acceptance_status: str, internal_certified: bool, phase: str, global_production: bool) -> bool:
    return bool(evidence_complete_flag and acceptance_status in {"ACCEPTED", "ACCEPTED_WITH_CONDITIONS"} and internal_certified and phase == "PHASE_4_LIMITED_PILOT_ACTIVATION" and not global_production)


def daily_status(*, required_data_complete: bool, critical_incident: bool, warnings: bool) -> str:
    if not required_data_complete:
        return "NO_DATA"
    if critical_incident:
        return "CRITICAL"
    return "HEALTHY_WITH_WARNINGS" if warnings else "HEALTHY"


def customer_action_allowed(*, consent: bool, human_approved: bool, policy_passed: bool, opted_out: bool) -> bool:
    return bool(consent and human_approved and policy_passed and not opted_out)
