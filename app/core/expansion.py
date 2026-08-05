"""Fail-closed staged production expansion contracts."""
from __future__ import annotations

from dataclasses import dataclass

EXPANSION_STATES = frozenset({"PLANNED", "AWAITING_APPROVAL", "APPROVED", "PRECHECK_RUNNING", "READY", "ACTIVE", "OBSERVING", "PAUSED", "FAILED", "ROLLING_BACK", "ROLLED_BACK", "COMPLETED", "BLOCKED"})
GATE_OUTCOMES = frozenset({"PASS", "PASS_WITH_WARNING", "PAUSE", "FAIL_ROLLBACK", "BLOCKED"})
TRANSITIONS = {
    "PLANNED": {"AWAITING_APPROVAL"}, "AWAITING_APPROVAL": {"APPROVED"},
    "APPROVED": {"PRECHECK_RUNNING"}, "PRECHECK_RUNNING": {"READY", "BLOCKED"},
    "READY": {"ACTIVE"}, "ACTIVE": {"OBSERVING", "PAUSED", "FAILED"},
    "OBSERVING": {"COMPLETED", "PAUSED", "FAILED"}, "FAILED": {"ROLLING_BACK"},
    "ROLLING_BACK": {"ROLLED_BACK"}, "PAUSED": {"READY"},
}


class ExpansionGateError(ValueError):
    pass


def transition(current: str, target: str) -> str:
    if current not in EXPANSION_STATES or target not in TRANSITIONS.get(current, set()):
        raise ExpansionGateError(f"invalid expansion transition: {current} -> {target}")
    return target


@dataclass(frozen=True)
class ObservationSnapshot:
    error_rate: float = 0.0
    duplicate_count: int = 0
    unauthorized_write_count: int = 0
    cross_tenant_count: int = 0
    critical_alert_count: int = 0
    reconciliation_backlog: int = 0
    postiz_outages: int = 0
    website_outages: int = 0
    live_calls: int = 0
    hopper_entries: int = 0


def evaluate_observation(snapshot: ObservationSnapshot, *, max_error_rate: float = 0.01, max_reconciliation_backlog: int = 0) -> str:
    if any((snapshot.duplicate_count, snapshot.unauthorized_write_count, snapshot.cross_tenant_count, snapshot.critical_alert_count, snapshot.postiz_outages, snapshot.website_outages, snapshot.live_calls, snapshot.hopper_entries)):
        return "FAIL_ROLLBACK"
    if snapshot.reconciliation_backlog > max_reconciliation_backlog or snapshot.error_rate > max_error_rate:
        return "PAUSE"
    return "PASS"
