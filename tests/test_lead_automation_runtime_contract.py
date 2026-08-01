from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.v1.n8n_lifecycle import FailureCallback, ResultCallback
from app.main import app


def _result(**overrides):
    values = {
        "schema_version": "1.0",
        "execution_id": "execution-staging-1",
        "event_id": "event-staging-1",
        "correlation_id": "correlation-staging-1",
        "idempotency_key": "result:execution-staging-1:event-staging-1",
        "event_type": "lead.hot",
        "environment": "staging",
        "originating_odoo_outbox_id": "odoo-outbox-staging-1",
        "originating_middleware_outbox_id": "middleware-outbox-staging-1",
        "created_at": datetime.now(UTC),
        "completed_at": datetime.now(UTC),
        "synthetic": True,
        "terminal_status": "SUCCEEDED",
        "result": {"summary": "internal-only"},
    }
    values.update(overrides)
    return values


def test_openapi_exposes_only_documented_lifecycle_endpoints():
    paths = TestClient(app).get("/openapi.json").json()["paths"]
    required = {
        "/api/v1/automation/events/verify",
        "/api/v1/integration/events/{event_id}/context",
        "/api/v1/n8n/executions",
        "/api/v1/n8n/internal-results",
        "/api/v1/n8n/acknowledgements",
        "/api/v1/n8n/results",
        "/api/v1/n8n/failures",
    }
    assert required <= set(paths)
    assert "/api/v1/commands" not in paths


def test_result_schema_is_staging_synthetic_and_binding_complete():
    assert ResultCallback.model_validate(_result()).event_type == "lead.hot"
    for field, value in (
        ("environment", "production"),
        ("synthetic", False),
        ("event_type", "call.completed"),
        ("originating_odoo_outbox_id", ""),
        ("originating_middleware_outbox_id", ""),
    ):
        with pytest.raises(ValidationError):
            ResultCallback.model_validate(_result(**{field: value}))


def test_failure_schema_is_bounded_and_redacted_by_shape():
    values = {
        "execution_id": "execution-staging-1",
        "event_id": "event-staging-1",
        "correlation_id": "correlation-staging-1",
        "idempotency_key": "event-idempotency-staging-1",
        "originating_odoo_outbox_id": "odoo-outbox-staging-1",
        "originating_middleware_outbox_id": "middleware-outbox-staging-1",
        "environment": "staging",
        "synthetic": True,
        "attempt": 5,
        "error_code": "workflow_failed",
        "error_summary": "bounded internal failure",
    }
    assert FailureCallback.model_validate(values).attempt == 5
    with pytest.raises(ValidationError):
        FailureCallback.model_validate({**values, "attempt": 6})
    with pytest.raises(ValidationError):
        FailureCallback.model_validate({**values, "error_summary": "x" * 513})
