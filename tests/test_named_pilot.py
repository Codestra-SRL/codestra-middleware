from app.core.named_pilot import CustomerPilotPreconditions, activation_allowed, customer_action_allowed, daily_status, evidence_complete


def preconditions(**kwargs):
    values = dict(customer_tenant_id="customer-1", workspace_ids=("w1",), business_owner="bo", pilot_owner="po", signed_authorization=True, approved_start="2026-01-01", approved_end="2026-01-31", approved_employees=("e1",), approved_tools=("knowledge.search",), approved_budget=True)
    values.update(kwargs)
    return CustomerPilotPreconditions(**values)


def test_customer_evidence_and_activation_are_gated():
    assert evidence_complete(preconditions())
    assert not evidence_complete(preconditions(signed_authorization=False))
    assert activation_allowed(evidence_complete_flag=True, acceptance_status="ACCEPTED", internal_certified=True, phase="PHASE_4_LIMITED_PILOT_ACTIVATION", global_production=False)
    assert not activation_allowed(evidence_complete_flag=True, acceptance_status="PENDING", internal_certified=True, phase="PHASE_4_LIMITED_PILOT_ACTIVATION", global_production=False)


def test_daily_status_never_marks_missing_data_healthy():
    assert daily_status(required_data_complete=False, critical_incident=False, warnings=False) == "NO_DATA"
    assert daily_status(required_data_complete=True, critical_incident=True, warnings=False) == "CRITICAL"
    assert daily_status(required_data_complete=True, critical_incident=False, warnings=True) == "HEALTHY_WITH_WARNINGS"


def test_customer_actions_require_consent_approval_policy_and_opt_out_check():
    assert customer_action_allowed(consent=True, human_approved=True, policy_passed=True, opted_out=False)
    assert not customer_action_allowed(consent=True, human_approved=True, policy_passed=True, opted_out=True)
    assert not customer_action_allowed(consent=True, human_approved=False, policy_passed=True, opted_out=False)
