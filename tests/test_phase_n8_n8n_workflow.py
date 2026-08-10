from scripts.render_phase_n8_n8n_workflow import CODE, workflow


def test_isolated_workflow_uses_only_standard_nodes_and_stays_inactive_in_git():
    document = workflow()
    assert document["active"] is False
    assert {node["type"] for node in document["nodes"]} == {
        "n8n-nodes-base.webhook",
        "n8n-nodes-base.code",
        "n8n-nodes-base.respondToWebhook",
    }
    assert "codestra-social-router-v1" in str(document)


def test_workflow_calls_authenticated_boundaries_and_never_dispatches_contact():
    for path in (
        "/api/v1/n8n-runtime/social-authorize",
        "/api/v1/identity/resolve",
        "/api/v1/leads",
        "/api/v1/odoo/leads/dry-run",
        "/api/v1/analytics/attribution/revenue",
        "/api/v1/n8n-runtime/results",
    ):
        assert path in CODE
    assert "X-Codestra-Signature" in CODE
    assert "automatic_contact:false" in CODE
    assert "external_actions:0" in CODE
    assert "SOCIAL_PUBLISH" not in CODE
    assert "VICIDIAL" not in CODE
