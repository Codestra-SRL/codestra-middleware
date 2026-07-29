from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.adapters.telephony.client import TelephonyClientError, TelephonyServiceClient
from app.core.telephony_commands import (
    LOGICAL_ENDPOINT_KEYS,
    MUTATION_ENDPOINTS,
    READBACK_ENDPOINTS,
    TelephonyCommandRequest,
    TelephonyCommandType,
)
from tests.test_endpoint_registry import endpoint


def command(**changes):
    values = {
        "schema_version": "1.0",
        "command_type": "telephony.asterisk.endpoint.apply",
        "aggregate_type": "agent",
        "aggregate_public_id": "AGT-SYNTHETIC-001",
        "aggregate_version": 4,
        "environment": "staging",
        "business_unit_public_id": "BU-SYNTHETIC-001",
        "campaign_public_id": "CMP-SYNTHETIC-001",
        "idempotency_key": "IDM-0000000000000001",
        "correlation_id": "COR-SYNTHETIC-001",
        "causation_id": "CAU-SYNTHETIC-001",
        "policy_decision_id": str(uuid4()),
        "policy_decision_hash": "a" * 64,
        "payload": {
            "endpoint_public_id": "EPT-SYNTHETIC-001",
            "agent_public_id": "AGT-SYNTHETIC-001",
            "allocation_reservation_id": "RSV-SYNTHETIC-001",
            "desired_state_version": 3,
        },
    }
    values.update(changes)
    return TelephonyCommandRequest.model_validate(values)


def test_all_command_routes_are_registry_keys_with_readback():
    assert set(MUTATION_ENDPOINTS.values()) <= LOGICAL_ENDPOINT_KEYS
    assert set(READBACK_ENDPOINTS.values()) <= LOGICAL_ENDPOINT_KEYS
    assert set(MUTATION_ENDPOINTS) == set(TelephonyCommandType)
    assert set(READBACK_ENDPOINTS) == set(TelephonyCommandType)


@pytest.mark.parametrize(
    "field",
    [
        "extension",
        "server_b_ip",
        "adapter_base_url",
        "ami_address",
        "vicidial_database_host",
        "context_name",
        "trunk_name",
        "customer_number",
    ],
)
def test_command_rejects_application_selected_resources(field):
    value = command().model_dump(mode="json")
    value["payload"][field] = "forbidden"
    with pytest.raises(ValidationError):
        TelephonyCommandRequest.model_validate(value)


def test_internal_call_is_bounded_to_staging_acceptance():
    base = command(
        command_type="telephony.asterisk.internal_call.create",
        payload={
            "call_public_id": "CALL-SYNTHETIC-001",
            "source_endpoint_public_id": "EPT-SOURCE-001",
            "destination_endpoint_public_id": "EPT-DESTINATION-001",
            "allocation_reservation_id": "RSV-SYNTHETIC-001",
            "desired_state_version": 1,
            "maximum_duration_seconds": 120,
            "purpose": "controlled_internal_acceptance",
        },
    )
    assert base.environment == "staging"
    with pytest.raises(ValidationError):
        TelephonyCommandRequest.model_validate(
            {**base.model_dump(mode="json"), "environment": "production"}
        )


class Resolver:
    def __init__(self, *, attestation_required=True):
        self.requests = []
        self.attestation_required = attestation_required

    async def resolve(self, request):
        self.requests.append(request)
        value = endpoint()
        return type(value)(
            **{
                **value.__dict__,
                "service_key": "telephony-adapter",
                "endpoint_key": request.endpoint_key,
                "target_attestation_required": self.attestation_required,
                "configuration_checksum": "sha256:" + "b" * 64,
            }
        )


class CommonClient:
    def __init__(self, resolver):
        self.resolver = resolver
        self.calls = []

    async def request_resolved(self, route, payload, **kwargs):
        self.calls.append((route, payload, kwargs))
        request = httpx.Request("POST", "https://invalid")
        return httpx.Response(
            202, json={"operation_id": str(uuid4())}, request=request
        )

    async def request(self, route, payload, **kwargs):
        self.calls.append((route, payload, kwargs))
        request = httpx.Request("POST" if route.mutation else "GET", "https://invalid")
        if route.mutation:
            return httpx.Response(
                202, json={"operation_id": str(uuid4())}, request=request
            )
        return httpx.Response(
            200,
            json={
                "desired_state": {
                    "endpoint_public_id": "EPT-SYNTHETIC-001",
                    "agent_public_id": "AGT-SYNTHETIC-001",
                    "allocation_reservation_id": "RSV-SYNTHETIC-001",
                    "desired_state_version": 3,
                    "state": "DISABLED",
                }
            },
            request=request,
        )


class Attestor:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.calls = []

    async def attest(self, **kwargs):
        self.calls.append(kwargs)
        return self.allowed


@pytest.mark.asyncio
async def test_dispatch_uses_registry_common_client_attestation_and_readback():
    resolver = Resolver()
    common = CommonClient(resolver)
    attestor = Attestor()
    client = TelephonyServiceClient(common, attestor)
    value = command()
    operation = await client.dispatch(
        "CMD-SYNTHETIC-001",
        value,
        traceparent="00-" + "1" * 32 + "-" + "2" * 16 + "-01",
    )
    assert resolver.requests[0].service_key == "telephony-adapter"
    assert resolver.requests[0].endpoint_key == "telephony.asterisk.endpoints.apply"
    assert resolver.requests[0].mutation is True
    assert attestor.calls[0]["configuration_checksum"].startswith("sha256:")
    assert common.calls[0][2]["idempotency_key"] == value.idempotency_key
    readback = await client.readback(
        value,
        operation,
        traceparent="00-" + "1" * 32 + "-" + "2" * 16 + "-01",
    )
    assert common.calls[1][0].endpoint_key == "telephony.asterisk.endpoints.read"
    assert common.calls[1][0].mutation is False
    assert readback["actual_hash"]
    assert readback["readback_matches"] is True


@pytest.mark.asyncio
async def test_dispatch_fails_closed_without_attestation():
    client = TelephonyServiceClient(CommonClient(Resolver()), Attestor(False))
    with pytest.raises(TelephonyClientError, match="attestation failed"):
        await client.dispatch(
            "CMD-SYNTHETIC-001",
            command(),
            traceparent="00-" + "1" * 32 + "-" + "2" * 16 + "-01",
        )


@pytest.mark.asyncio
async def test_dispatch_rejects_route_that_does_not_require_attestation():
    client = TelephonyServiceClient(
        CommonClient(Resolver(attestation_required=False)), Attestor()
    )
    with pytest.raises(TelephonyClientError, match="must require attestation"):
        await client.dispatch(
            "CMD-SYNTHETIC-001",
            command(),
            traceparent="00-" + "1" * 32 + "-" + "2" * 16 + "-01",
        )


@pytest.mark.parametrize(
    ("command_type", "payload"),
    [
        (
            "telephony.vicidial.user.apply",
            {
                "endpoint_public_id": "EPT-WRONG-001",
                "allocation_reservation_id": "RSV-001",
                "desired_state_version": 1,
            },
        ),
        (
            "telephony.vicidial.phone.apply",
            {
                "agent_public_id": "AGT-WRONG-001",
                "allocation_reservation_id": "RSV-001",
                "desired_state_version": 1,
            },
        ),
        (
            "telephony.asterisk.call.hangup",
            {
                "endpoint_public_id": "EPT-WRONG-001",
                "allocation_reservation_id": "RSV-001",
                "desired_state_version": 1,
            },
        ),
    ],
)
def test_command_specific_target_is_required(command_type, payload):
    with pytest.raises(ValidationError):
        command(command_type=command_type, payload=payload)
