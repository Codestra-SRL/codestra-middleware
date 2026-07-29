from datetime import UTC, datetime, timedelta

import pytest

from app.core.automation import canonical_hash
from app.core.generic_events import (
    EventSchema,
    GenericEventError,
    SchemaRegistry,
    validate_generic_event,
)


def event_payload(**overrides):
    now = datetime.now(UTC).replace(microsecond=0)
    payload = {"operation": "reconciliation.run"}
    value = {
        "schema_version": "1.0",
        "event_id": "EVT-1",
        "event_type": "reconciliation.run",
        "event_version": 1,
        "idempotency_key": "IDM-1",
        "correlation_id": "COR-1",
        "causation_id": "CAU-1",
        "environment": "staging",
        "organization_public_id": "ORG-1",
        "business_unit_public_id": "BU-1",
        "campaign_public_id": "CMP-1",
        "producer": {"service_key": "codestra-odoo", "version": "1.0.0"},
        "policy": {"version": "1", "hash": "sha256:" + "a" * 64},
        "occurred_at": now,
        "expires_at": now + timedelta(minutes=5),
        "payload_hash": "sha256:" + canonical_hash(payload),
        "payload": payload,
    }
    value.update(overrides)
    return value


@pytest.fixture
def registry():
    return SchemaRegistry(
        (EventSchema("reconciliation.run", "1.0", "codestra-odoo", frozenset({"operation"})),)
    )


def test_generic_event_is_strict_and_deterministic(registry):
    result = validate_generic_event(event_payload(), registry=registry, expected_environment="staging")
    assert result.event_id == "EVT-1"


@pytest.mark.parametrize("field", ["event_type", "payload", "idempotency_key"])
def test_missing_envelope_field_is_rejected(registry, field):
    value = event_payload()
    del value[field]
    with pytest.raises(GenericEventError) as error:
        validate_generic_event(value, registry=registry, expected_environment="staging")
    assert error.value.status_code == 400


def test_unknown_event_type_is_rejected(registry):
    with pytest.raises(GenericEventError) as error:
        validate_generic_event(event_payload(event_type="unknown.event"), registry=registry, expected_environment="staging")
    assert error.value.code == "EVENT_TYPE_UNSUPPORTED"
    assert error.value.status_code == 422


def test_payload_hash_conflict_is_rejected(registry):
    with pytest.raises(GenericEventError) as error:
        validate_generic_event(event_payload(payload_hash="sha256:" + "b" * 64), registry=registry, expected_environment="staging")
    assert error.value.code == "EVENT_PAYLOAD_HASH_MISMATCH"
    assert error.value.status_code == 409


def test_expired_and_wrong_environment_are_fail_closed(registry):
    expired = event_payload(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(GenericEventError) as error:
        validate_generic_event(expired, registry=registry, expected_environment="staging")
    assert error.value.status_code == 410
    with pytest.raises(GenericEventError) as error:
        validate_generic_event(event_payload(environment="production"), registry=registry, expected_environment="staging")
    assert error.value.status_code == 403

