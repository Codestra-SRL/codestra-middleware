from datetime import UTC, datetime, timedelta

from app.core.production_certification import (
    SECTION_12_GATES,
    MaintenanceWindow,
    ProductionCertificationEvidence,
    certify_production,
    disaster_recovery_evidence_valid,
    rollback_evidence_valid,
    validate_feature_flags,
    validate_maintenance_window,
    validate_strategy,
)


def _evidence(**overrides):
    values = {
        "release_id": "rel-12",
        "version": "2026.08.05",
        "environment": "production",
        "strategy": "CANARY",
        "canary_scope": "internal_extension",
        "gates": {gate: True for gate in SECTION_12_GATES},
        "release_owner": "release-owner",
        "security_owner": "security-owner",
        "rollback_authority": "rollback-owner",
        "backup_reference": "backup-1",
        "restore_reference": "restore-1",
        "rollback_reference": "rollback-1",
        "disaster_recovery_reference": "dr-1",
        "maintenance_window_reference": "mw-1",
        "feature_flags": {
            "release_management_enabled": True,
            "release_staging_enabled": True,
            "release_rollback_enabled": True,
            "release_production_enabled": False,
            "automatic_production_deployment_enabled": False,
            "automatic_production_rollback_enabled": False,
        },
        "production_activation": False,
    }
    values.update(overrides)
    return ProductionCertificationEvidence(**values)


def test_certification_requires_every_gate_and_keeps_activation_disabled():
    assert certify_production(_evidence()) == (True, "CERTIFIED_FOR_CONTROLLED_PLANNING")
    assert certify_production(_evidence(production_activation=True))[1] == "ACTIVATION_NOT_AUTHORIZED"
    gates = {gate: True for gate in SECTION_12_GATES}
    gates["RESTORE_VERIFIED"] = False
    assert certify_production(_evidence(gates=gates))[1] == "RELEASE_GATE_FAILED"


def test_feature_flags_and_strategies_fail_closed():
    flags = {"release_management_enabled": True, "release_staging_enabled": True, "release_rollback_enabled": True}
    assert validate_feature_flags(flags, environment="staging") == (True, "VALID")
    assert validate_feature_flags({**flags, "release_production_enabled": True}, environment="production")[1] == "PRODUCTION_ACTION_FLAG_ENABLED"
    assert validate_strategy("CANARY", canary_scope="internal_extension", rollback_reference="r1")[0]
    assert validate_strategy("CANARY", canary_scope="", rollback_reference="r1")[1] == "CANARY_SCOPE_REQUIRED"


def test_maintenance_rollback_and_dr_evidence_require_references():
    window = MaintenanceWindow(datetime.now(UTC), datetime.now(UTC) + timedelta(hours=1), "UTC", "ops", "notice-1")
    assert validate_maintenance_window(window) == (True, "VALID")
    assert rollback_evidence_valid(authorized=True, rehearsed=True, target_version="v0", verification_reference="check-1")
    assert not rollback_evidence_valid(authorized=True, rehearsed=False, target_version="v0", verification_reference="check-1")
    assert disaster_recovery_evidence_valid(backup_verified=True, restore_verified=True, rpo_seconds=300, rto_seconds=900, evidence_reference="dr-1")
