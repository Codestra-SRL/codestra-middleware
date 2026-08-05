"""Fail-closed licensing-gap and controlled-pilot policy contracts."""
from dataclasses import dataclass

PILOT_STATES = frozenset({"DRAFT", "GOVERNANCE_REVIEW", "LEGAL_REVIEW", "SECURITY_REVIEW", "READY_FOR_SYNTHETIC_TEST", "BLOCKED", "APPROVED_PENDING_ACTIVATION", "ACTIVE_DISABLED", "ROLLED_BACK", "CLOSED"})
CLASSIFICATIONS = frozenset({"INTENDED", "NOT_INTENDED", "UNCERTAIN", "PROHIBITED_UNTIL_APPROVED"})


@dataclass(frozen=True)
class PilotAdmission:
    tenant_id: str
    account_id: str
    synthetic_only: bool
    compliance_approved: bool
    security_approved: bool
    legal_approved: bool
    real_money: bool = False


@dataclass(frozen=True)
class KillSwitch:
    reason: str
    privileged: bool
    trading_disabled: bool
    funding_disabled: bool


def validate_classification(value: str) -> str:
    if value not in CLASSIFICATIONS:
        raise ValueError("business-model classification requires approved value")
    return value


def admit_pilot(admission: PilotAdmission) -> bool:
    return bool(admission.tenant_id and admission.account_id and admission.synthetic_only and admission.compliance_approved and admission.security_approved and admission.legal_approved and not admission.real_money)


def activate_kill_switch(switch: KillSwitch) -> bool:
    return bool(switch.reason.strip() and switch.privileged and switch.trading_disabled and switch.funding_disabled)
