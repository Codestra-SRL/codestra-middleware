from app.core.ai_tool_gateway import (
    ToolRequest,
    classify_error,
    idempotency_replay,
    retry_allowed,
    same_scope,
    validate_request,
)


def request(**kwargs):
    values = dict(employee_id="e1", employee_version="v1", task_id="t1", tenant_id="tenant-a", workspace_id="w1", tool_code="odoo.crm.read", tool_version="v1", action="read", reason="approved task", input={}, idempotency_key="idem-1", trace_id="trace-1", permission_granted=True)
    values.update(kwargs)
    return ToolRequest(**values)


def test_requests_fail_closed_and_require_approval_for_approval_tools():
    assert validate_request(request()) == (True, "VALID")
    assert validate_request(request(tenant_id=""))[1] == "MISSING_CONTEXT"
    assert validate_request(request(permission_granted=False))[1] == "PERMISSION_DENIED"
    assert validate_request(request(approval_required=True))[1] == "APPROVAL_REQUIRED"


def test_prohibited_actions_never_reach_an_adapter():
    assert validate_request(request(action="trading.live.execute"))[1] == "PROHIBITED_ACTION"
    assert validate_request(request(risk_level="PROHIBITED"))[1] == "PROHIBITED_ACTION"


def test_retry_and_idempotency_are_bounded():
    assert classify_error("TIMEOUT") == "RETRYABLE"
    assert retry_allowed("TIMEOUT", 0, 2)
    assert not retry_allowed("TIMEOUT", 2, 2)
    assert not retry_allowed("PERMISSION_DENIED", 0, 2)
    assert idempotency_replay(existing_key="idem-1", request_key="idem-1")
    assert not idempotency_replay(existing_key="idem-1", request_key="idem-2")


def test_records_are_exactly_tenant_and_workspace_scoped():
    assert same_scope(tenant_id="t1", workspace_id="w1", record_tenant_id="t1", record_workspace_id="w1")
    assert not same_scope(tenant_id="t1", workspace_id="w1", record_tenant_id="t2", record_workspace_id="w1")
    assert not same_scope(tenant_id="t1", workspace_id="w1", record_tenant_id="t1", record_workspace_id="w2")
