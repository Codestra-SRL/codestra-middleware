from app.main import app
from app.api.v1.ai import KNOWN_AI_WORKFLOWS, WorkflowResult


def test_canonical_workflow_result_route_is_registered():
    paths = set(app.openapi()["paths"])
    assert "/api/v1/workflow-results" in paths
    assert "CDA-AI-03" in KNOWN_AI_WORKFLOWS


def test_workflow_result_contract_requires_schema_and_execution_identity():
    result = WorkflowResult(
        message_id="msg-1",
        event_id="evt-1",
        job_id="00000000-0000-0000-0000-000000000001",
        tenant_id="tenant-test",
        correlation_id="corr-1",
        workflow_id="CDA-AI-03",
        workflow_execution_id="exec-1",
        result_type="lead.normalized",
        result_schema="lead_normalization_v1",
        result_schema_version=1,
        status="completed",
        payload={"confidence": 0.5},
    )
    assert result.workflow_id == "CDA-AI-03"
