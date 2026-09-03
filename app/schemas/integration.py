"""Strict common integration contracts for separated middleware services."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal, Mapping, Self, cast
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


PUBLIC_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
HASH_PATTERN = r"^[a-f0-9]{64}$"
TYPE_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$"
EVENT_FAMILIES = frozenset(
    {
        "campaign",
        "agent",
        "extension",
        "endpoint",
        "lead",
        "call",
        "callback",
        "transfer",
        "feature",
        "provisioning",
        "reconciliation",
        "dead_letter",
    }
)
MAX_PAYLOAD_DEPTH = 16
MAX_PAYLOAD_NODES = 4096
MAX_CANONICAL_PAYLOAD_BYTES = 262_144
MAX_COMMAND_TTL_SECONDS = 900
FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "database_password",
        "hmac_secret",
        "password",
        "private_key",
        "sip_secret",
        "token",
    }
)


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class PiiClassification(StrEnum):
    NONE = "NONE"
    INTERNAL = "INTERNAL"
    PERSONAL = "PERSONAL"
    SENSITIVE = "SENSITIVE"
    REGULATED = "REGULATED"


class RequesterType(StrEnum):
    USER = "USER"
    SERVICE = "SERVICE"
    WORKFLOW = "WORKFLOW"
    SYSTEM = "SYSTEM"


class CommandStatus(StrEnum):
    REQUESTED = "REQUESTED"
    VALIDATING = "VALIDATING"
    VALIDATED = "VALIDATED"
    AUTHORIZING = "AUTHORIZING"
    AUTHORIZED = "AUTHORIZED"
    RESERVED = "RESERVED"
    DISPATCHING = "DISPATCHING"
    DISPATCHED = "DISPATCHED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    COMPLETED = "COMPLETED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    DEAD_LETTER = "DEAD_LETTER"
    REPLAY_APPROVAL_REQUIRED = "REPLAY_APPROVAL_REQUIRED"
    REJECTED = "REJECTED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


class CommandType(StrEnum):
    CAMPAIGN_REGISTER = "campaign.register"
    CAMPAIGN_PROVISION = "campaign.provision"
    CAMPAIGN_ACTIVATE = "campaign.activate"
    CAMPAIGN_PAUSE = "campaign.pause"
    AGENT_PROVISION = "agent.provision"
    AGENT_MOVE = "agent.move"
    AGENT_SUSPEND = "agent.suspend"
    AGENT_TERMINATE = "agent.terminate"
    EXTENSION_RESERVE = "extension.reserve"
    EXTENSION_ASSIGN = "extension.assign"
    EXTENSION_RETIRE = "extension.retire"
    ENDPOINT_PROVISION = "endpoint.provision"
    ENDPOINT_REVOKE = "endpoint.revoke"
    VICIDIAL_CAMPAIGN_CREATE = "vicidial.campaign.create"
    VICIDIAL_LIST_CREATE = "vicidial.list.create"
    VICIDIAL_LEAD_UPSERT = "vicidial.lead.upsert"
    VICIDIAL_AGENT_PROVISION = "vicidial.agent.provision"
    VICIDIAL_PHONE_PROVISION = "vicidial.phone.provision"
    VICIDIAL_DISPOSITION_WRITE = "vicidial.disposition.write"
    CALLBACK_SCHEDULE = "callback.schedule"
    CALLBACK_DISPATCH = "callback.dispatch"
    CALLBACK_CANCEL = "callback.cancel"
    TRANSFER_AUTHORIZE = "transfer.authorize"
    TRANSFER_BEGIN_CONSULTATION = "transfer.begin_consultation"
    TRANSFER_COMPLETE = "transfer.complete"
    TRANSFER_RECOVER = "transfer.recover"
    FEATURE_PREPARE = "feature.prepare"
    FEATURE_ACTIVATE = "feature.activate"
    FEATURE_DEACTIVATE = "feature.deactivate"
    RECONCILIATION_RUN = "reconciliation.run"
    DEAD_LETTER_REPLAY = "dead_letter.replay"


COMMAND_TRANSITIONS: dict[CommandStatus, frozenset[CommandStatus]] = {
    CommandStatus.REQUESTED: frozenset(
        {CommandStatus.VALIDATING, CommandStatus.REJECTED}
    ),
    CommandStatus.VALIDATING: frozenset(
        {CommandStatus.VALIDATED, CommandStatus.REJECTED, CommandStatus.FAILED}
    ),
    CommandStatus.VALIDATED: frozenset(
        {CommandStatus.AUTHORIZING, CommandStatus.REJECTED}
    ),
    CommandStatus.AUTHORIZING: frozenset(
        {CommandStatus.AUTHORIZED, CommandStatus.REJECTED}
    ),
    CommandStatus.AUTHORIZED: frozenset(
        {CommandStatus.RESERVED, CommandStatus.REJECTED}
    ),
    CommandStatus.RESERVED: frozenset(
        {CommandStatus.DISPATCHING, CommandStatus.ROLLED_BACK, CommandStatus.FAILED}
    ),
    CommandStatus.DISPATCHING: frozenset(
        {
            CommandStatus.DISPATCHED,
            CommandStatus.DEAD_LETTER,
            CommandStatus.FAILED,
        }
    ),
    CommandStatus.DISPATCHED: frozenset(
        {
            CommandStatus.ACKNOWLEDGED,
            CommandStatus.RECONCILIATION_REQUIRED,
            CommandStatus.FAILED,
        }
    ),
    CommandStatus.ACKNOWLEDGED: frozenset(
        {CommandStatus.COMPLETED, CommandStatus.RECONCILIATION_REQUIRED}
    ),
    CommandStatus.RETRY_SCHEDULED: frozenset(
        {CommandStatus.DEAD_LETTER, CommandStatus.REPLAY_APPROVAL_REQUIRED}
    ),
    CommandStatus.DEAD_LETTER: frozenset(
        {CommandStatus.REPLAY_APPROVAL_REQUIRED}
    ),
    CommandStatus.REPLAY_APPROVAL_REQUIRED: frozenset(
        {CommandStatus.VALIDATING, CommandStatus.REJECTED}
    ),
    CommandStatus.RECONCILIATION_REQUIRED: frozenset(
        {
            CommandStatus.COMPLETED,
            CommandStatus.ROLLED_BACK,
            CommandStatus.FAILED,
        }
    ),
    CommandStatus.COMPLETED: frozenset(),
    CommandStatus.REJECTED: frozenset(),
    CommandStatus.ROLLED_BACK: frozenset(),
    CommandStatus.FAILED: frozenset(),
}


def require_command_transition(
    current: CommandStatus, target: CommandStatus
) -> None:
    if target not in COMMAND_TRANSITIONS[current]:
        raise ValueError(f"invalid command transition: {current.value}->{target.value}")


class CommonCommandEnvelope(ContractModel):
    schema_version: Literal["codestra.command.v1"]
    command_id: UUID
    command_type: CommandType
    idempotency_key: str = Field(min_length=1, max_length=255)
    correlation_id: UUID
    causation_id: UUID | None = None
    organization_id: str = Field(pattern=PUBLIC_ID_PATTERN)
    business_unit_id: str = Field(pattern=PUBLIC_ID_PATTERN)
    campaign_id: str = Field(pattern=PUBLIC_ID_PATTERN)
    aggregate_type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    aggregate_id: str = Field(pattern=PUBLIC_ID_PATTERN)
    environment: Environment
    policy_version: str = Field(min_length=1, max_length=64)
    policy_hash: str = Field(pattern=HASH_PATTERN)
    requested_by_type: RequesterType
    requested_by_id: str = Field(pattern=PUBLIC_ID_PATTERN)
    approved_by_id: str | None = Field(default=None, pattern=PUBLIC_ID_PATTERN)
    requested_at: AwareDatetime
    expires_at: AwareDatetime
    pii_classification: PiiClassification
    desired_version: int = Field(ge=1)
    payload_hash: str = Field(pattern=HASH_PATTERN)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_integrity_and_time(self) -> Self:
        if self.expires_at <= self.requested_at:
            raise ValueError("expires_at must be after requested_at")
        if (self.expires_at - self.requested_at).total_seconds() > MAX_COMMAND_TTL_SECONDS:
            raise ValueError("command validity window exceeds maximum")
        if self.environment is Environment.PRODUCTION:
            if self.approved_by_id is None:
                raise ValueError("production command requires approved_by_id")
            if self.approved_by_id == self.requested_by_id:
                raise ValueError("production command requires independent approval")
        if canonical_payload_hash(self.payload) != self.payload_hash:
            raise ValueError("payload hash mismatch")
        object.__setattr__(self, "payload", deep_freeze_payload(self.payload))
        return self

    @field_serializer("payload")
    def serialize_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return thaw_payload(payload)


class CommonEventEnvelope(ContractModel):
    schema_version: Literal["codestra.event.v1"]
    event_id: UUID
    event_type: str = Field(pattern=TYPE_PATTERN, max_length=128)
    event_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=255)
    correlation_id: UUID
    causation_id: UUID | None = None
    organization_id: str = Field(pattern=PUBLIC_ID_PATTERN)
    business_unit_id: str = Field(pattern=PUBLIC_ID_PATTERN)
    campaign_id: str = Field(pattern=PUBLIC_ID_PATTERN)
    aggregate_type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    aggregate_id: str = Field(pattern=PUBLIC_ID_PATTERN)
    source_system: str = Field(pattern=PUBLIC_ID_PATTERN)
    producer_identity: str = Field(pattern=PUBLIC_ID_PATTERN)
    environment: Environment
    policy_hash: str = Field(pattern=HASH_PATTERN)
    occurred_at: AwareDatetime
    recorded_at: AwareDatetime
    payload_hash: str = Field(pattern=HASH_PATTERN)
    pii_classification: PiiClassification
    payload: dict[str, Any]

    @field_validator("event_type")
    @classmethod
    def validate_event_family(cls, value: str) -> str:
        if value.partition(".")[0] not in EVENT_FAMILIES:
            raise ValueError("unsupported event family")
        return value

    @model_validator(mode="after")
    def validate_integrity_and_time(self) -> Self:
        if self.recorded_at < self.occurred_at:
            raise ValueError("recorded_at cannot precede occurred_at")
        if canonical_payload_hash(self.payload) != self.payload_hash:
            raise ValueError("payload hash mismatch")
        object.__setattr__(self, "payload", deep_freeze_payload(self.payload))
        return self

    @field_serializer("payload")
    def serialize_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return thaw_payload(payload)


def _normalize_json(
    value: Any, *, depth: int = 0, counter: list[int] | None = None
) -> Any:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > MAX_PAYLOAD_NODES:
        raise ValueError("payload node limit exceeded")
    if depth > MAX_PAYLOAD_DEPTH:
        raise ValueError("payload depth limit exceeded")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not -(2**63) <= value < 2**63:
            raise ValueError("payload integer outside signed 64-bit range")
        return value
    if isinstance(value, float):
        raise ValueError("floating-point payload values are unsupported")
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise ValueError("payload strings must use Unicode NFC")
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("payload object keys must be strings")
            if unicodedata.normalize("NFC", key) != key:
                raise ValueError("payload keys must use Unicode NFC")
            if key.casefold() in FORBIDDEN_SECRET_KEYS:
                raise ValueError("payload contains a forbidden secret field")
            normalized[key] = _normalize_json(
                item, depth=depth + 1, counter=counter
            )
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            _normalize_json(item, depth=depth + 1, counter=counter)
            for item in value
        ]
    raise ValueError("payload contains a non-JSON value")


def canonical_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    normalized = _normalize_json(payload)
    encoded = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > MAX_CANONICAL_PAYLOAD_BYTES:
        raise ValueError("canonical payload exceeds size limit")
    return encoded


def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def deep_freeze_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized = _normalize_json(payload)

    def freeze(value: Any) -> Any:
        if isinstance(value, dict):
            return MappingProxyType({key: freeze(item) for key, item in value.items()})
        if isinstance(value, list):
            return tuple(freeze(item) for item in value)
        return value

    return cast(Mapping[str, Any], freeze(normalized))


def thaw_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    def thaw(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {key: thaw(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return [thaw(item) for item in value]
        return value

    return cast(dict[str, Any], thaw(payload))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_common_command(raw: bytes) -> CommonCommandEnvelope:
    body = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    return CommonCommandEnvelope.model_validate(body)


def parse_common_event(raw: bytes) -> CommonEventEnvelope:
    body = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    return CommonEventEnvelope.model_validate(body)


def export_contract_schemas() -> dict[str, dict[str, Any]]:
    return {
        "codestra.command.v1.schema.json": CommonCommandEnvelope.model_json_schema(),
        "codestra.event.v1.schema.json": CommonEventEnvelope.model_json_schema(),
    }
