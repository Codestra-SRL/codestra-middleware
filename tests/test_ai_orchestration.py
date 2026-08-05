from app.core.ai_orchestration import DispatchRequest, authorize_dispatch, emergency_blocks, initial_task_state, retry_allowed


def request(**overrides):
    values = dict(tenant_id="t1", workspace_id="w1", employee_id="e1", department_id="d1", goal_id="g1", task_id="task-1", workflow_code="CDA-AI-01", workflow_version="1", idempotency_key="idem-1", trace_id="trace-1", employee_active=True, department_active=True, goal_active=True, permission_granted=True, approval_required=False, approval_granted=False, workflow_approved=True)
    values.update(overrides)
    return DispatchRequest(**values)


def test_dispatch_requires_all_governance_gates():
    assert authorize_dispatch(request()) == (True, "AUTHORIZED")
    assert authorize_dispatch(request(permission_granted=False))[1] == "PERMISSION_DENIED"
    assert authorize_dispatch(request(workflow_approved=False))[1] == "WORKFLOW_APPROVAL_REQUIRED"
    assert authorize_dispatch(request(approval_required=True))[1] == "HUMAN_APPROVAL_REQUIRED"
    assert authorize_dispatch(request(emergency_state="PAUSE_NEW_WORK"))[1] == "EMERGENCY_CONTROL_ACTIVE"


def test_task_state_retry_and_emergency_controls_are_bounded():
    assert initial_task_state(approval_required=True) == "WAITING_FOR_APPROVAL"
    assert initial_task_state(approval_required=False) == "QUEUED"
    assert retry_allowed(failure_class="TIMEOUT", attempt=0, maximum_attempts=3)
    assert not retry_allowed(failure_class="PERMISSION_DENIED", attempt=0, maximum_attempts=3)
    assert not retry_allowed(failure_class="TIMEOUT", attempt=3, maximum_attempts=3)
    assert emergency_blocks("SHUTDOWN")
    assert not emergency_blocks("CLEAR")

