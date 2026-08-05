"""Fail-closed Section 12 release and production-certification contracts."""

from dataclasses import dataclass
from datetime import datetime

SECTION_12_GATES = frozenset(
    {
        "ARCHITECTURE_REVIEW",
        "SECURITY_REVIEW",
        "PERFORMANCE_REVIEW",
        "REGRESSION",
        "BACKUP_VERIFIED",
        "RESTORE_VERIFIED",
        "TENANT_ISOLATION",
        "AI_SAFETY",
        "WORKFLOW_SAFETY",
        "MARKETPLACE_SAFETY",
        "VOICE_SAFETY",
        "COMMERCIAL_VALIDATION",
        "DOCUMENTATION",
        "EXECUTIVE_APPROVAL",
        "CHANGE_APPROVAL",
        "MONITORING_READY",
        "MAINTENANCE_WINDOW",
        "ROLLBACK_REHEARSED",
        "DR_VALIDATED",
        "FEATURE_FLAGS_VALIDATED",
        "GO_LIVE_CHECKLIST",
    }
)
DEPLOYMENT_STRATEGIES = frozenset(
    {"STAGING_ONLY", "FEATURE_FLAG", "CANARY", "BLUE_GREEN", "ROLLING", "MAINTENANCE", "EMERGENCY_HOTFIX"}
)
PROHIBITED_PRODUCTION_FLAGS = frozenset(
    {
        "release_production_enabled",
        "automatic_production_deployment_enabled",
        "automatic_production_rollback_enabled",
        "automatic_customer_data_deletion_enabled",
        "global_unrestricted_production_enabled",
    }
)


@dataclass(frozen=True)
class ProductionCertificationEvidence:
    release_id: str
    version: str
    environment: str
    strategy: str
    canary_scope: str
    gates: dict[str, bool]
    release_owner: str
    security_owner: str
    rollback_authority: str
    backup_reference: str
    restore_reference: str
    rollback_reference: str
    disaster_recovery_reference: str
    maintenance_window_reference: str
    feature_flags: dict[str, bool]
    production_activation: bool = False


@dataclass(frozen=True)
class MaintenanceWindow:
    starts_at: datetime
    ends_at: datetime
    timezone: str
    approved_by: str
    customer_notice_reference: str


def validate_feature_flags(flags: dict[str, bool], *, environment: str) -> tuple[bool, str]:
    if environment not in {"development", "testing", "qa", "staging", "pilot", "production", "dr", "training", "sandbox"}:
        return False, "INVALID_ENVIRONMENT"
    if any(flags.get(name, False) for name in PROHIBITED_PRODUCTION_FLAGS):
        return False, "PRODUCTION_ACTION_FLAG_ENABLED"
    required_safe = ("release_management_enabled", "release_staging_enabled", "release_rollback_enabled")
    if not all(flags.get(name, False) for name in required_safe):
        return False, "RELEASE_CONTROL_FLAG_MISSING"
    return True, "VALID"


def validate_maintenance_window(window: MaintenanceWindow) -> tuple[bool, str]:
    if window.ends_at <= window.starts_at:
        return False, "INVALID_WINDOW"
    if not window.timezone.strip() or not window.approved_by.strip() or not window.customer_notice_reference.strip():
        return False, "INCOMPLETE_WINDOW_EVIDENCE"
    return True, "VALID"


def validate_strategy(strategy: str, *, canary_scope: str = "", rollback_reference: str = "") -> tuple[bool, str]:
    if strategy not in DEPLOYMENT_STRATEGIES:
        return False, "INVALID_STRATEGY"
    if strategy == "CANARY" and canary_scope not in {"internal_extension", "test_campaign", "named_agents", "approved_test_did"}:
        return False, "CANARY_SCOPE_REQUIRED"
    if strategy in {"CANARY", "BLUE_GREEN", "ROLLING", "MAINTENANCE", "EMERGENCY_HOTFIX"} and not rollback_reference.strip():
        return False, "ROLLBACK_REFERENCE_REQUIRED"
    return True, "VALID"


def certify_production(evidence: ProductionCertificationEvidence) -> tuple[bool, str]:
    if not evidence.release_id.strip() or not evidence.version.strip() or evidence.environment != "production":
        return False, "INVALID_CERTIFICATION_SCOPE"
    strategy_ok, strategy_reason = validate_strategy(evidence.strategy, canary_scope=evidence.canary_scope, rollback_reference=evidence.rollback_reference)
    if not strategy_ok:
        return False, strategy_reason
    if evidence.production_activation:
        return False, "ACTIVATION_NOT_AUTHORIZED"
    if len({evidence.release_owner, evidence.security_owner, evidence.rollback_authority}) != 3:
        return False, "SEPARATION_OF_DUTIES_REQUIRED"
    if not all((evidence.release_owner, evidence.security_owner, evidence.rollback_authority)):
        return False, "APPROVAL_IDENTITIES_REQUIRED"
    if not all((evidence.backup_reference, evidence.restore_reference, evidence.rollback_reference, evidence.disaster_recovery_reference, evidence.maintenance_window_reference)):
        return False, "RELEASE_EVIDENCE_INCOMPLETE"
    if set(evidence.gates) != SECTION_12_GATES or not all(evidence.gates.values()):
        return False, "RELEASE_GATE_FAILED"
    flags_ok, flags_reason = validate_feature_flags(evidence.feature_flags, environment=evidence.environment)
    if not flags_ok:
        return False, flags_reason
    return True, "CERTIFIED_FOR_CONTROLLED_PLANNING"


def rollback_evidence_valid(*, authorized: bool, rehearsed: bool, target_version: str, verification_reference: str) -> bool:
    return bool(authorized and rehearsed and target_version.strip() and verification_reference.strip())


def disaster_recovery_evidence_valid(*, backup_verified: bool, restore_verified: bool, rpo_seconds: int, rto_seconds: int, evidence_reference: str) -> bool:
    return bool(backup_verified and restore_verified and rpo_seconds >= 0 and rto_seconds > 0 and evidence_reference.strip())
