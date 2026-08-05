from app.core.ai_collaboration import (
    DEPARTMENT_STATES,
    HANDOFF_STATES,
    DelegationRequest,
    authorize_collaboration,
    authorize_delegation,
    cross_department_allowed,
)


def delegation(**kwargs):
    values = dict(source_employee="e1", target_employee="e2", source_tenant="t1", target_tenant="t1", source_workspace="w1", target_workspace="w1", depth=1, participant_count=2, completion_criteria="return structured result")
    values.update(kwargs)
    return DelegationRequest(**values)


def test_states_and_collaboration_scope_are_bounded():
    assert {"DRAFT", "STAGING_ACTIVE", "SUSPENDED"}.issubset(DEPARTMENT_STATES)
    assert {"WAITING_FOR_ACCEPTANCE", "COMPLETED", "ESCALATED"}.issubset(HANDOFF_STATES)
    assert authorize_collaboration(tenant_id="t1", workspace_id="w1", owning_tenant_id="t1", owning_workspace_id="w1", participant_count=8, budget_remaining=True)
    assert not authorize_collaboration(tenant_id="t1", workspace_id="w1", owning_tenant_id="t2", owning_workspace_id="w1", participant_count=1, budget_remaining=True)


def test_delegation_rejects_self_scope_suspension_and_limits():
    assert authorize_delegation(delegation()) == (True, "VALID")
    assert authorize_delegation(delegation(source_employee="e1", target_employee="e1"))[1] == "SELF_DELEGATION"
    assert authorize_delegation(delegation(target_tenant="t2"))[1] == "SCOPE_MISMATCH"
    assert authorize_delegation(delegation(depth=4))[1] == "LIMIT_EXCEEDED"
    assert authorize_delegation(delegation(target_suspended=True))[1] == "TARGET_SUSPENDED"
    assert authorize_delegation(delegation(self_approval=True))[1] == "SELF_APPROVAL"


def test_cross_department_requests_require_approval_and_same_tenant():
    assert cross_department_allowed(source_department="SALES", target_department="FINANCE", approved=True, same_tenant=True)
    assert not cross_department_allowed(source_department="SALES", target_department="FINANCE", approved=False, same_tenant=True)
    assert not cross_department_allowed(source_department="SALES", target_department="FINANCE", approved=True, same_tenant=False)
