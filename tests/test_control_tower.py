from app.core.control_tower import EmergencyControl, ExecutiveAction, authorize_action, authorize_emergency_control, correlate_alerts, metric_usable


def test_executive_actions_require_approval_mfa_and_block_prohibited_actions():
    base = dict(tenant_id="t1", workspace_id="w1", actor_id="u1", action="open_incident", privileged=False, mfa_verified=False, approved=True, idempotency_key="k1")
    assert authorize_action(ExecutiveAction(**base)) == (True, "VALID")
    assert authorize_action(ExecutiveAction(**{**base, "approved": False}))[1] == "APPROVAL_REQUIRED"
    assert authorize_action(ExecutiveAction(**{**base, "action": "transfer_money"}))[1] == "PROHIBITED_ACTION"
    assert authorize_action(ExecutiveAction(**{**base, "privileged": True}))[1] == "MFA_REQUIRED"


def test_stale_or_unavailable_metrics_are_not_usable():
    assert metric_usable(freshness="CURRENT", source="billing", updated_at="2026-01-01T00:00:00Z")
    assert not metric_usable(freshness="STALE", source="billing", updated_at="2026-01-01T00:00:00Z")
    assert not metric_usable(freshness="CURRENT", source="", updated_at="2026-01-01T00:00:00Z")


def test_alert_correlation_requires_all_evidence_types():
    assert correlate_alerts(alert_types={"QWEN_DOWN", "AI_FAILURES"}, required_types={"QWEN_DOWN", "AI_FAILURES"})
    assert not correlate_alerts(alert_types={"QWEN_DOWN"}, required_types={"QWEN_DOWN", "AI_FAILURES"})


def test_emergency_controls_require_privileged_mfa_approval_and_no_auto_reenable():
    base = dict(tenant_id="t1", workspace_id="w1", actor_id="u1", state="PAUSE_ALL_WORK", scope="tenant:t1", reason="synthetic incident", privileged=True, mfa_verified=True, approved=True, idempotency_key="emergency-1")
    assert authorize_emergency_control(EmergencyControl(**base)) == (True, "VALID")
    assert authorize_emergency_control(EmergencyControl(**{**base, "mfa_verified": False}))[1] == "PRIVILEGED_MFA_REQUIRED"
    assert authorize_emergency_control(EmergencyControl(**{**base, "automatic_reenable": True}))[1] == "AUTOMATIC_REENABLE_PROHIBITED"
