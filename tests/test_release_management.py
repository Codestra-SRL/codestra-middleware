from app.core.release_management import ReleaseReadiness, authorize_release, feature_flag_change_allowed, rollback_allowed


def test_release_requires_all_gates_human_approval_and_rollback():
    base = dict(release_id="r1", version="v1", release_type="PLATFORM", required_gates=frozenset({"SECURITY", "REGRESSION"}), passed_gates=frozenset({"SECURITY", "REGRESSION"}), human_approved=True, rollback_ready=True)
    assert authorize_release(ReleaseReadiness(**base)) == (True, "READY")
    assert authorize_release(ReleaseReadiness(**{**base, "human_approved": False}))[1] == "APPROVAL_REQUIRED"
    assert authorize_release(ReleaseReadiness(**{**base, "rollback_ready": False}))[1] == "ROLLBACK_NOT_READY"
    assert authorize_release(ReleaseReadiness(**{**base, "passed_gates": frozenset({"SECURITY"})}))[1] == "GATE_FAILED"


def test_feature_flags_and_rollback_require_human_controls():
    assert feature_flag_change_allowed(actor_id="u1", approved=True, environment="staging", production=False)
    assert not feature_flag_change_allowed(actor_id="u1", approved=False, environment="staging", production=False)
    assert rollback_allowed(authorized=True, rehearsed=True, target_version="v0")
    assert not rollback_allowed(authorized=True, rehearsed=False, target_version="v0")
