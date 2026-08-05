"""Fail-closed release, change, approval, and rollback contracts."""
from dataclasses import dataclass

RELEASE_TYPES = frozenset({"PLATFORM", "AI", "MARKETPLACE", "VOICE", "SECURITY_PATCH", "HOTFIX", "INFRASTRUCTURE", "DATABASE", "CUSTOMER_CONFIGURATION", "FEATURE_FLAG"})
GATES = frozenset({"ARCHITECTURE", "SECURITY", "PERFORMANCE", "REGRESSION", "BACKUP", "RESTORE", "TENANT_ISOLATION", "AI_SAFETY", "WORKFLOW_SAFETY", "MARKETPLACE_SAFETY", "VOICE_SAFETY", "COMMERCIAL", "DOCUMENTATION", "EXECUTIVE"})


@dataclass(frozen=True)
class ReleaseReadiness:
    release_id: str
    version: str
    release_type: str
    required_gates: frozenset[str]
    passed_gates: frozenset[str]
    human_approved: bool
    rollback_ready: bool


def authorize_release(readiness: ReleaseReadiness) -> tuple[bool, str]:
    if not readiness.release_id or not readiness.version or readiness.release_type not in RELEASE_TYPES:
        return False, "INVALID_RELEASE"
    if not readiness.required_gates.issubset(GATES) or not readiness.required_gates.issubset(readiness.passed_gates):
        return False, "GATE_FAILED"
    if not readiness.human_approved:
        return False, "APPROVAL_REQUIRED"
    if not readiness.rollback_ready:
        return False, "ROLLBACK_NOT_READY"
    return True, "READY"


def feature_flag_change_allowed(*, actor_id: str, approved: bool, environment: str, production: bool) -> bool:
    return bool(actor_id and approved and environment and not (production and environment != "production"))


def rollback_allowed(*, authorized: bool, rehearsed: bool, target_version: str) -> bool:
    return bool(authorized and rehearsed and target_version)
