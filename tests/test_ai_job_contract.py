import pytest
from pydantic import ValidationError

from app.api.v1.ai import AIJobCreate, _contains_sensitive, _request_hash


def payload(**overrides):
    value = {
        "tenant_id": "tenant-codestra",
        "workspace_id": "sales",
        "service_code": "lead_intelligence",
        "task_code": "score_business_lead",
        "input_payload": {"company_name": "Synthetic Roofing"},
        "idempotency_key": "synthetic-ai-job-0001",
        "environment": "test",
    }
    value.update(overrides)
    return value


def test_ai_job_contract_is_strict_and_hash_is_stable():
    first = AIJobCreate.model_validate(payload())
    second = AIJobCreate.model_validate(payload())
    assert _request_hash(first) == _request_hash(second)
    with pytest.raises(ValidationError):
        AIJobCreate.model_validate(payload(extra_field="rejected"))


def test_ai_job_rejects_nested_secrets_before_outbox_creation():
    assert _contains_sensitive({"context": [{"api_key": "never"}]})
    assert not _contains_sensitive({"company_name": "Synthetic Roofing"})


def test_ai_job_approval_and_environment_are_explicit():
    job = AIJobCreate.model_validate(
        payload(requires_approval=True, environment="staging")
    )
    assert job.requires_approval is True
    assert job.environment == "staging"
