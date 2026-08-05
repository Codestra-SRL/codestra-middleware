from app.core.ai_pilot import ALLOWLIST, AUTONOMY_LEVELS, PilotAdmission, authorize_admission, emergency_suspend, pilot_limits_ok


def admission(**kwargs):
    values = dict(pilot_id="p1", tenant_id="t1", workspace_id="w1", employee_id="e1", autonomy_level="LEVEL_2_DRAFT_ONLY", human_owner_id="human-1", action="email.draft", readiness_passed=True, budget_available=True)
    values.update(kwargs)
    return PilotAdmission(**values)


def test_autonomy_levels_and_allowlist_are_explicit():
    assert "LEVEL_4_LIMITED_AUTONOMY" in AUTONOMY_LEVELS
    assert "email.draft" in ALLOWLIST
    assert authorize_admission(admission()) == (True, "VALID")
    assert authorize_admission(admission(action="transfer.money"))[1] == "ACTION_NOT_ALLOWLISTED"
    assert authorize_admission(admission(autonomy_level="LEVEL_5_PROHIBITED_DURING_PILOT"))[1] == "AUTONOMY_DISABLED"


def test_admission_requires_readiness_budget_owner_and_suspension_state():
    assert authorize_admission(admission(readiness_passed=False))[1] == "READINESS_GATE_FAILED"
    assert authorize_admission(admission(budget_available=False))[1] == "BUDGET_EXCEEDED"
    assert authorize_admission(admission(human_owner_id=""))[1] == "MISSING_CONTEXT"
    assert authorize_admission(admission(suspended=True))[1] == "PILOT_SUSPENDED"


def test_pilot_limits_and_emergency_suspend_require_human_control():
    assert pilot_limits_ok(tenant_count=3, workspace_count=6, employee_count=8, level4_count=2)
    assert not pilot_limits_ok(tenant_count=4, workspace_count=1, employee_count=1, level4_count=1)
    assert emergency_suspend(operator_id="human-1", mfa_verified=True, reason="test")
    assert not emergency_suspend(operator_id="human-1", mfa_verified=False, reason="test")
