from datetime import UTC, datetime

import pytest

from app.core.enterprise_events import EnterpriseEventError, EventEnvelope, idempotency_hash


def event(**updates):
    values = dict(
        event_id="evt-1",
        aggregate_type="customer",
        aggregate_id="customer-1",
        aggregate_sequence=1,
        event_type="customer.created",
        schema_version="1.0",
        payload={"name": "Synthetic Customer"},
        occurred_at=datetime.now(UTC),
        correlation_id="correlation-1",
    )
    values.update(updates)
    return EventEnvelope(**values)


def test_valid_event_envelope():
    event().validate()


@pytest.mark.parametrize("value", ["CustomerCreated", "customer", "customer..created", "customer/created"])
def test_invalid_event_type_is_rejected(value):
    with pytest.raises(EnterpriseEventError):
        event(event_type=value).validate()


def test_sequence_must_be_positive():
    with pytest.raises(EnterpriseEventError):
        event(aggregate_sequence=0).validate()


def test_payload_is_bounded():
    with pytest.raises(EnterpriseEventError):
        event(payload={"value": "x" * 262_145}).validate()


def test_idempotency_is_scoped_by_tenant_and_workspace():
    first = idempotency_hash("tenant-a", "workspace-a", "request-1")
    assert first != idempotency_hash("tenant-b", "workspace-a", "request-1")
    assert first != idempotency_hash("tenant-a", "workspace-b", "request-1")


def test_migration_enforces_immutability_and_bounded_replay():
    text = open("migrations/versions/0031_enterprise_event_store.py").read()
    assert "enterprise_event_immutable" in text
    assert "BEFORE UPDATE OR DELETE" in text
    assert "attempts BETWEEN 0 AND 5" in text
    assert "uq_enterprise_event_idempotency" in text


def test_oidc_exemption_is_exact_not_a_broad_api_prefix():
    text = open("app/main.py").read()
    assert '"/api/v1/events"' in text
    assert 'startswith("/api/v1/events")' not in text
    assert "OIDC_EVENT_PATH.fullmatch" in text


def test_every_event_endpoint_uses_validated_identity_context():
    text = open("app/api/v1/enterprise_events.py").read()
    assert "_identity(authorization)" in text
    assert text.count("_context(authorization") == 5
    assert 'Header("", alias="X-Tenant' not in text
