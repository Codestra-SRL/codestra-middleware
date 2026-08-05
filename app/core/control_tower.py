"""Fail-closed contracts for executive visibility and controlled actions."""
from dataclasses import dataclass

FRESHNESS_STATES = frozenset({"CURRENT", "DELAYED", "STALE", "UNAVAILABLE", "UNKNOWN"})
SERVICE_STATES = frozenset({"HEALTHY", "DEGRADED", "PARTIAL_OUTAGE", "MAJOR_OUTAGE", "MAINTENANCE", "UNKNOWN", "DISABLED"})
EMERGENCY_CONTROL_STATES = frozenset({"PAUSE_NEW_WORK", "PAUSE_ALL_WORK", "REVOKE_TOOLS", "READ_ONLY", "SHUTDOWN"})


@dataclass(frozen=True)
class ExecutiveAction:
    tenant_id: str
    workspace_id: str
    actor_id: str
    action: str
    privileged: bool
    mfa_verified: bool
    approved: bool
    idempotency_key: str


@dataclass(frozen=True)
class EmergencyControl:
    tenant_id: str
    workspace_id: str
    actor_id: str
    state: str
    scope: str
    reason: str
    privileged: bool
    mfa_verified: bool
    approved: bool
    idempotency_key: str
    automatic_reenable: bool = False


def authorize_action(action: ExecutiveAction) -> tuple[bool, str]:
    if not all((action.tenant_id, action.workspace_id, action.actor_id, action.action, action.idempotency_key)):
        return False, "MISSING_CONTEXT"
    if action.action in {"transfer_money", "execute_live_trade", "delete_production", "create_privileged_user", "disable_audit"}:
        return False, "PROHIBITED_ACTION"
    if action.privileged and not action.mfa_verified:
        return False, "MFA_REQUIRED"
    if not action.approved:
        return False, "APPROVAL_REQUIRED"
    return True, "VALID"


def authorize_emergency_control(control: EmergencyControl) -> tuple[bool, str]:
    if not all((control.tenant_id, control.workspace_id, control.actor_id, control.scope, control.reason, control.idempotency_key)):
        return False, "MISSING_CONTEXT"
    if control.state not in EMERGENCY_CONTROL_STATES:
        return False, "INVALID_CONTROL_STATE"
    if not control.privileged or not control.mfa_verified:
        return False, "PRIVILEGED_MFA_REQUIRED"
    if not control.approved:
        return False, "APPROVAL_REQUIRED"
    if control.automatic_reenable:
        return False, "AUTOMATIC_REENABLE_PROHIBITED"
    return True, "VALID"


def metric_usable(*, freshness: str, source: str, updated_at: str) -> bool:
    return bool(freshness in FRESHNESS_STATES and freshness != "STALE" and freshness != "UNAVAILABLE" and source and updated_at)


def correlate_alerts(*, alert_types: set[str], required_types: set[str]) -> bool:
    return required_types.issubset(alert_types)
