"""Strict telephony command and result contracts.

Commands reference public identities and committed allocation reservations.  They
never carry a selected extension, host, URL, database address, dialplan context,
or trunk name.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


PUBLIC_ID = re.compile(r"^[A-Z][A-Z0-9_]{1,15}-[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$")


class TelephonyCommandType(StrEnum):
    USER_APPLY = "telephony.vicidial.user.apply"
    USER_DISABLE = "telephony.vicidial.user.disable"
    PHONE_APPLY = "telephony.vicidial.phone.apply"
    PHONE_DISABLE = "telephony.vicidial.phone.disable"
    ENDPOINT_APPLY = "telephony.asterisk.endpoint.apply"
    ENDPOINT_DISABLE = "telephony.asterisk.endpoint.disable"
    CONTACT_REVOKE = "telephony.asterisk.contact.revoke"
    INTERNAL_CALL_CREATE = "telephony.asterisk.internal_call.create"
    CALL_HANGUP = "telephony.asterisk.call.hangup"
    RECONCILIATION_CREATE = "telephony.reconciliation.create"


class TelephonyCommandState(StrEnum):
    RECEIVED = "RECEIVED"
    POLICY_PENDING = "POLICY_PENDING"
    POLICY_DENIED = "POLICY_DENIED"
    AUTHORIZED = "AUTHORIZED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    READBACK_PENDING = "READBACK_PENDING"
    SUCCEEDED = "SUCCEEDED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    FAILED_TRANSIENT = "FAILED_TRANSIENT"
    FAILED_PERMANENT = "FAILED_PERMANENT"


MUTATION_ENDPOINTS: dict[TelephonyCommandType, str] = {
    TelephonyCommandType.USER_APPLY: "telephony.vicidial.users.apply",
    TelephonyCommandType.USER_DISABLE: "telephony.vicidial.users.disable",
    TelephonyCommandType.PHONE_APPLY: "telephony.vicidial.phones.apply",
    TelephonyCommandType.PHONE_DISABLE: "telephony.vicidial.phones.disable",
    TelephonyCommandType.ENDPOINT_APPLY: "telephony.asterisk.endpoints.apply",
    TelephonyCommandType.ENDPOINT_DISABLE: "telephony.asterisk.endpoints.disable",
    TelephonyCommandType.CONTACT_REVOKE: "telephony.asterisk.contacts.revoke",
    TelephonyCommandType.INTERNAL_CALL_CREATE: "telephony.asterisk.internal_calls.create",
    TelephonyCommandType.CALL_HANGUP: "telephony.asterisk.calls.hangup",
    TelephonyCommandType.RECONCILIATION_CREATE: "telephony.reconciliation.create",
}

READBACK_ENDPOINTS: dict[TelephonyCommandType, str] = {
    TelephonyCommandType.USER_APPLY: "telephony.vicidial.users.read",
    TelephonyCommandType.USER_DISABLE: "telephony.vicidial.users.read",
    TelephonyCommandType.PHONE_APPLY: "telephony.vicidial.phones.read",
    TelephonyCommandType.PHONE_DISABLE: "telephony.vicidial.phones.read",
    TelephonyCommandType.ENDPOINT_APPLY: "telephony.asterisk.endpoints.read",
    TelephonyCommandType.ENDPOINT_DISABLE: "telephony.asterisk.endpoints.read",
    TelephonyCommandType.CONTACT_REVOKE: "telephony.asterisk.contacts.list",
    TelephonyCommandType.INTERNAL_CALL_CREATE: "telephony.asterisk.calls.read",
    TelephonyCommandType.CALL_HANGUP: "telephony.asterisk.calls.read",
    TelephonyCommandType.RECONCILIATION_CREATE: "telephony.reconciliation.read",
}

LOGICAL_ENDPOINT_KEYS = frozenset(
    {
        "telephony.vicidial.users.read",
        "telephony.vicidial.users.apply",
        "telephony.vicidial.users.disable",
        "telephony.vicidial.phones.read",
        "telephony.vicidial.phones.apply",
        "telephony.vicidial.phones.disable",
        "telephony.vicidial.campaigns.read",
        "telephony.vicidial.leads.read",
        "telephony.asterisk.endpoints.read",
        "telephony.asterisk.endpoints.apply",
        "telephony.asterisk.endpoints.disable",
        "telephony.asterisk.contacts.list",
        "telephony.asterisk.contacts.revoke",
        "telephony.asterisk.dialplan.read",
        "telephony.asterisk.runtime.read",
        "telephony.asterisk.internal_calls.create",
        "telephony.asterisk.calls.read",
        "telephony.asterisk.calls.hangup",
        "telephony.reconciliation.create",
        "telephony.reconciliation.read",
    }
)

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "extension",
        "server_b_ip",
        "adapter_base_url",
        "ami_address",
        "vicidial_database_host",
        "pjsip_context",
        "context_name",
        "trunk",
        "trunk_name",
        "telephone_number",
        "customer_number",
        "destination_number",
    }
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


class TelephonyCommandPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    endpoint_public_id: str | None = Field(default=None, max_length=144)
    agent_public_id: str | None = Field(default=None, max_length=144)
    phone_public_id: str | None = Field(default=None, max_length=144)
    call_public_id: str | None = Field(default=None, max_length=144)
    contact_id: str | None = Field(default=None, max_length=128)
    allocation_reservation_id: str = Field(min_length=4, max_length=144)
    desired_state_version: int = Field(ge=1)
    maximum_duration_seconds: int | None = Field(default=None, ge=1, le=300)
    purpose: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_public_ids(self) -> TelephonyCommandPayload:
        values = (
            self.endpoint_public_id,
            self.agent_public_id,
            self.phone_public_id,
            self.call_public_id,
        )
        if not any(values):
            raise ValueError("at least one target public ID is required")
        for value in values:
            if value and not PUBLIC_ID.fullmatch(value):
                raise ValueError("invalid target public ID")
        return self


class TelephonyCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = Field(pattern=r"^1[.]0$")
    command_type: TelephonyCommandType
    aggregate_type: str = Field(min_length=1, max_length=64)
    aggregate_public_id: str = Field(min_length=4, max_length=144)
    aggregate_version: int = Field(ge=1)
    environment: str = Field(pattern=r"^(staging|test|production)$")
    business_unit_public_id: str = Field(min_length=4, max_length=144)
    campaign_public_id: str = Field(min_length=4, max_length=144)
    idempotency_key: str = Field(min_length=8, max_length=255)
    correlation_id: str = Field(min_length=8, max_length=128)
    causation_id: str = Field(min_length=1, max_length=128)
    policy_decision_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    policy_decision_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: TelephonyCommandPayload

    @model_validator(mode="after")
    def forbid_application_selected_resources(self) -> TelephonyCommandRequest:
        raw = self.payload.model_dump(exclude_none=True)
        if FORBIDDEN_PAYLOAD_KEYS.intersection(raw):
            raise ValueError("application-selected telephony resource is prohibited")
        if (
            self.command_type is TelephonyCommandType.INTERNAL_CALL_CREATE
            and (
                self.environment != "staging"
                or self.payload.maximum_duration_seconds is None
                or self.payload.purpose != "controlled_internal_acceptance"
            )
        ):
            raise ValueError("internal calls require bounded staging acceptance scope")
        return self

    def request_hash(self) -> str:
        return payload_hash(self.model_dump(mode="json"))


class TelephonyOperationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation_id: str
    command_id: str
    state: TelephonyCommandState
    endpoint_key: str
    readback_endpoint_key: str
    target_configuration_checksum: str
    target_attested: bool
    desired_hash: str
    actual_hash: str | None = None
    readback_matches: bool | None = None
    correlation_id: str
    completed_at: datetime | None = None


def new_command_record(command: TelephonyCommandRequest) -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "command_type": command.command_type.value,
        "aggregate_type": command.aggregate_type,
        "aggregate_public_id": command.aggregate_public_id,
        "aggregate_version": command.aggregate_version,
        "environment": command.environment,
        "business_unit_public_id": command.business_unit_public_id,
        "campaign_public_id": command.campaign_public_id,
        "idempotency_hash": hashlib.sha256(command.idempotency_key.encode()).hexdigest(),
        "request_hash": command.request_hash(),
        "correlation_id": command.correlation_id,
        "causation_id": command.causation_id,
        "policy_decision_id": command.policy_decision_id,
        "policy_decision_hash": command.policy_decision_hash,
        "payload_json": command.payload.model_dump(mode="json", exclude_none=True),
        "state": TelephonyCommandState.POLICY_PENDING.value,
        "created_at": now,
        "updated_at": now,
    }
