from app.core.ai_workforce import (
    EMPLOYEE_STATUSES,
    TASK_STATES,
    Delegation,
    MemoryRequest,
    ToolRequest,
    allow_delegation,
    authorize_memory,
    authorize_tool,
)


def test_employee_and_task_states_are_fail_closed():
    assert {"DRAFT", "STAGING_ACTIVE", "SUSPENDED"}.issubset(EMPLOYEE_STATUSES)
    assert {"WAITING_FOR_APPROVAL", "RUNNING", "RECONCILIATION_REQUIRED"}.issubset(TASK_STATES)


def test_tool_authorization_requires_permission_and_approval():
    base = dict(tenant_id="t1", workspace_id="w1", employee_id="e1", required_permission="reports.read", granted_permissions=frozenset({"reports.read"}), risk_level="READ_ONLY")
    assert authorize_tool(ToolRequest(**base, approval_required=False, approved=False))
    assert not authorize_tool(ToolRequest(**{**base, "granted_permissions": frozenset()}, approval_required=False, approved=False))
    assert not authorize_tool(ToolRequest(**base, approval_required=True, approved=False))
    assert not authorize_tool(ToolRequest(**{**base, "risk_level": "HIGH_RISK"}, approval_required=False, approved=True))


def test_memory_is_exactly_tenant_and_workspace_scoped():
    assert authorize_memory(MemoryRequest("t1", "w1", "t1", "w1", True))
    assert not authorize_memory(MemoryRequest("t1", "w1", "t2", "w1", True))
    assert not authorize_memory(MemoryRequest("t1", "w1", "t1", "w2", True))


def test_delegation_is_bounded_and_same_tenant():
    assert allow_delegation(Delegation(3, 5, "t1", "t1"))
    assert not allow_delegation(Delegation(4, 1, "t1", "t1"))
    assert not allow_delegation(Delegation(1, 1, "t2", "t1"))
