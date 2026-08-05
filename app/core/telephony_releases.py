"""Telephony release gates; production activation remains approval-only."""

from dataclasses import dataclass

RELEASE_STATES = frozenset({"DRAFT", "VALIDATING", "TESTING", "SECURITY_REVIEW", "READY_FOR_STAGING", "STAGING_DEPLOYED", "STAGING_VALIDATED", "READY_FOR_PRODUCTION_REVIEW", "APPROVED", "SCHEDULED", "DEPLOYING", "MONITORING", "COMPLETED", "FAILED", "ROLLBACK_REQUIRED", "ROLLING_BACK", "ROLLED_BACK", "CANCELLED"})


@dataclass(frozen=True)
class ReleaseGateSet:
    backup_verified: bool
    rollback_verified: bool
    security_passed: bool
    routing_passed: bool
    monitoring_ready: bool


def production_release_ready(gates: ReleaseGateSet) -> bool:
    return all((gates.backup_verified, gates.rollback_verified, gates.security_passed, gates.routing_passed, gates.monitoring_ready))
