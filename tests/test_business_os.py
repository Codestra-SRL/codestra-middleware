from app.core.business_os import CommandRequest, graph_edge_allowed, universal_result_allowed, validate_command


def test_command_bar_is_scoped_and_allowlisted():
    base = dict(tenant_id="t1", workspace_id="w1", actor_id="u1", action="FIND", query="customer", idempotency_key="k1")
    assert validate_command(CommandRequest(**base)) == (True, "VALID")
    assert validate_command(CommandRequest(**{**base, "action": "DELETE"}))[1] == "ACTION_NOT_ALLOWLISTED"
    assert validate_command(CommandRequest(**{**base, "action": "CREATE_DRAFT"}))[1] == "APPROVAL_REQUIRED"


def test_graph_and_universal_results_cannot_cross_scope():
    assert graph_edge_allowed(source_tenant="t1", target_tenant="t1", source_workspace="w1", target_workspace="w1")
    assert not graph_edge_allowed(source_tenant="t1", target_tenant="t2", source_workspace="w1", target_workspace="w1")
    assert universal_result_allowed(tenant_id="t1", workspace_id="w1", result_tenant="t1", result_workspace="w1")
    assert not universal_result_allowed(tenant_id="t1", workspace_id="w1", result_tenant="t1", result_workspace="w2")
