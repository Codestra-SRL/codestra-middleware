from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.integration import (
    CommandStatus,
    CommonCommandEnvelope,
    CommonEventEnvelope,
    canonical_payload_hash,
    export_contract_schemas,
    parse_common_command,
    parse_common_event,
    require_command_transition,
)


def command_data() -> dict:
    now = datetime.now(UTC)
    payload = {"extension": 7110, "disabled": True}
    return {
        "schema_version": "codestra.command.v1",
        "command_id": uuid4(),
        "command_type": "extension.reserve",
        "idempotency_key": "test-extension-7110",
        "correlation_id": uuid4(),
        "causation_id": None,
        "organization_id": "ORG-CODESTRA",
        "business_unit_id": "BU-RLP",
        "campaign_id": "CMP-100-RLP",
        "aggregate_type": "extension",
        "aggregate_id": "100-A-7110",
        "environment": "test",
        "policy_version": "v1",
        "policy_hash": "a" * 64,
        "requested_by_type": "SERVICE",
        "requested_by_id": "test-suite",
        "approved_by_id": None,
        "requested_at": now,
        "expires_at": now + timedelta(minutes=5),
        "pii_classification": "INTERNAL",
        "desired_version": 1,
        "payload_hash": canonical_payload_hash(payload),
        "payload": payload,
    }


def event_data() -> dict:
    now = datetime.now(UTC)
    payload = {"state": "PROPOSED_DISABLED"}
    return {
        "schema_version": "codestra.event.v1",
        "event_id": uuid4(),
        "event_type": "campaign.registered",
        "event_version": 1,
        "idempotency_key": "campaign-register-100",
        "correlation_id": uuid4(),
        "causation_id": uuid4(),
        "organization_id": "ORG-CODESTRA",
        "business_unit_id": "BU-RLP",
        "campaign_id": "CMP-100-RLP",
        "aggregate_type": "campaign",
        "aggregate_id": "CMP-100-RLP",
        "source_system": "codestra-policy-api",
        "producer_identity": "policy-api-production",
        "environment": "test",
        "policy_hash": "a" * 64,
        "occurred_at": now,
        "recorded_at": now,
        "payload_hash": canonical_payload_hash(payload),
        "pii_classification": "INTERNAL",
        "payload": payload,
    }


def test_common_command_accepts_complete_strict_envelope() -> None:
    command = CommonCommandEnvelope.model_validate(command_data())
    assert command.command_type.value == "extension.reserve"


def test_common_command_rejects_unknown_fields() -> None:
    body = command_data()
    body["unexpected"] = True
    with pytest.raises(ValidationError):
        CommonCommandEnvelope.model_validate(body)


def test_common_command_rejects_payload_hash_mismatch() -> None:
    body = command_data()
    body["payload"]["extension"] = 7111
    with pytest.raises(ValidationError, match="payload hash mismatch"):
        CommonCommandEnvelope.model_validate(body)


def test_common_command_rejects_unknown_command_type() -> None:
    body = command_data()
    body["command_type"] = "database.execute"
    with pytest.raises(ValidationError):
        CommonCommandEnvelope.model_validate(body)


def test_common_command_rejects_nonpositive_validity_window() -> None:
    body = command_data()
    body["expires_at"] = body["requested_at"]
    with pytest.raises(ValidationError, match="expires_at"):
        CommonCommandEnvelope.model_validate(body)


def test_common_event_accepts_complete_strict_envelope() -> None:
    event = CommonEventEnvelope.model_validate(event_data())
    assert event.event_type == "campaign.registered"


def test_common_event_rejects_hash_mismatch() -> None:
    body = event_data()
    body["payload"]["state"] = "ACTIVE"
    with pytest.raises(ValidationError, match="payload hash mismatch"):
        CommonEventEnvelope.model_validate(body)


def test_common_event_rejects_unknown_event_family() -> None:
    body = event_data()
    body["event_type"] = "database.executed"
    with pytest.raises(ValidationError, match="unsupported event family"):
        CommonEventEnvelope.model_validate(body)


def test_common_event_rejects_recorded_before_occurred() -> None:
    body = event_data()
    body["recorded_at"] = body["occurred_at"] - timedelta(seconds=1)
    with pytest.raises(ValidationError, match="recorded_at"):
        CommonEventEnvelope.model_validate(body)


def test_common_contracts_reject_naive_timestamps() -> None:
    command = command_data()
    command["requested_at"] = command["requested_at"].replace(tzinfo=None)
    with pytest.raises(ValidationError):
        CommonCommandEnvelope.model_validate(command)


def test_validated_payload_is_deeply_immutable() -> None:
    body = command_data()
    body["payload"] = {"nested": {"values": [1, 2]}}
    body["payload_hash"] = canonical_payload_hash(body["payload"])
    command = CommonCommandEnvelope.model_validate(body)
    with pytest.raises(TypeError):
        command.payload["nested"]["values"][0] = 9


def test_command_serialization_round_trip_preserves_hash_and_payload() -> None:
    command = CommonCommandEnvelope.model_validate(command_data())
    parsed = parse_common_command(command.model_dump_json().encode())
    assert parsed.payload_hash == command.payload_hash
    assert parsed.model_dump(mode="json")["payload"] == command_data()["payload"]


def test_event_serialization_round_trip_preserves_hash_and_payload() -> None:
    event = CommonEventEnvelope.model_validate(event_data())
    parsed = parse_common_event(event.model_dump_json().encode())
    assert parsed.payload_hash == event.payload_hash
    assert parsed.model_dump(mode="json")["payload"] == event_data()["payload"]


@pytest.mark.parametrize(
    "payload",
    [
        {"value": 1.0},
        {1: "not-a-string-key"},
        {"value": "e\u0301"},
        {"value": 2**63},
    ],
)
def test_canonical_payload_rejects_ambiguous_values(payload: dict) -> None:
    with pytest.raises(ValueError):
        canonical_payload_hash(payload)


def test_canonical_payload_rejects_raw_secret_fields() -> None:
    with pytest.raises(ValueError, match="forbidden secret field"):
        canonical_payload_hash({"nested": {"password": "must-not-enter-envelope"}})


def test_raw_command_parser_rejects_duplicate_json_keys() -> None:
    raw = b'{"schema_version":"codestra.command.v1","schema_version":"other"}'
    with pytest.raises(ValueError, match="duplicate JSON key"):
        parse_common_command(raw)


def test_raw_event_parser_rejects_duplicate_nested_json_keys() -> None:
    raw = b'{"payload":{"state":"A","state":"B"}}'
    with pytest.raises(ValueError, match="duplicate JSON key"):
        parse_common_event(raw)


def test_production_command_requires_independent_approval() -> None:
    body = command_data()
    body["environment"] = "production"
    with pytest.raises(ValidationError, match="approved_by_id"):
        CommonCommandEnvelope.model_validate(body)
    body["approved_by_id"] = body["requested_by_id"]
    with pytest.raises(ValidationError, match="independent approval"):
        CommonCommandEnvelope.model_validate(body)


def test_production_command_accepts_distinct_approval_identity() -> None:
    body = command_data()
    body["environment"] = "production"
    body["approved_by_id"] = "independent-reviewer"
    assert CommonCommandEnvelope.model_validate(body).approved_by_id


def test_command_ttl_is_bounded() -> None:
    body = command_data()
    body["expires_at"] = body["requested_at"] + timedelta(minutes=16)
    with pytest.raises(ValidationError, match="validity window"):
        CommonCommandEnvelope.model_validate(body)


def test_contract_schema_exports_are_closed() -> None:
    schemas = export_contract_schemas()
    assert set(schemas) == {
        "codestra.command.v1.schema.json",
        "codestra.event.v1.schema.json",
    }
    assert all(schema["additionalProperties"] is False for schema in schemas.values())


def test_checked_in_contract_schemas_match_exact_export() -> None:
    root = Path(__file__).resolve().parents[1]
    for filename, schema in export_contract_schemas().items():
        expected = json.dumps(schema, indent=2, sort_keys=True) + "\n"
        assert (root / "schemas" / filename).read_text(encoding="utf-8") == expected


def test_command_lifecycle_cannot_jump_requested_to_completed() -> None:
    with pytest.raises(ValueError, match="invalid command transition"):
        require_command_transition(CommandStatus.REQUESTED, CommandStatus.COMPLETED)


def test_command_lifecycle_accepts_ordered_first_transition() -> None:
    require_command_transition(CommandStatus.REQUESTED, CommandStatus.VALIDATING)


def test_terminal_command_status_cannot_transition() -> None:
    with pytest.raises(ValueError, match="invalid command transition"):
        require_command_transition(CommandStatus.COMPLETED, CommandStatus.DISPATCHING)


def test_default_lifecycle_disallows_retry_dispatch_and_replay_reservation() -> None:
    with pytest.raises(ValueError, match="invalid command transition"):
        require_command_transition(
            CommandStatus.DISPATCHING, CommandStatus.RETRY_SCHEDULED
        )
    with pytest.raises(ValueError, match="invalid command transition"):
        require_command_transition(
            CommandStatus.REPLAY_APPROVAL_REQUIRED, CommandStatus.RESERVED
        )


def test_replay_requires_fresh_validation() -> None:
    require_command_transition(
        CommandStatus.REPLAY_APPROVAL_REQUIRED, CommandStatus.VALIDATING
    )
