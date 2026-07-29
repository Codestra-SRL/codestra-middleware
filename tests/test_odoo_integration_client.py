from typing import Any

import httpx
import pytest

from app.adapters.odoo.client import OdooIntegrationClient, OdooRequestContext


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, dict[str, Any], dict[str, Any]]] = []

    async def request(self, route, payload, **kwargs):
        self.calls.append((route, payload, kwargs))
        return httpx.Response(200, json={"persisted": True})


def context() -> OdooRequestContext:
    return OdooRequestContext(
        environment="test",
        organization_public_id="ORG-TEST",
        business_unit_public_id="BU-TEST",
        campaign_public_id="CMP-TEST",
        request_id="REQ-1",
        correlation_id="COR-1",
        causation_id="CAU-1",
        traceparent="00-" + "1" * 32 + "-" + "2" * 16 + "-01",
    )


@pytest.mark.asyncio
async def test_outbox_operations_use_logical_endpoint_keys():
    transport = RecordingClient()
    client = OdooIntegrationClient(transport)

    await client.claim_outbox(context(), {"batch_size": 50}, "IDM-CLAIM")
    await client.renew_outbox_lease(
        context(), "OUT-1", {"lease_generation": 2}, "IDM-RENEW"
    )
    await client.acknowledge_outbox(
        context(), "OUT-1", {"lease_generation": 2}, "IDM-ACK"
    )
    await client.release_outbox(
        context(), "OUT-1", {"lease_generation": 2}, "IDM-RELEASE"
    )

    assert [call[0].endpoint_key for call in transport.calls] == [
        "outbox.claim",
        "outbox.renew",
        "outbox.acknowledge",
        "outbox.release",
    ]
    assert all(call[0].service_key == "odoo" for call in transport.calls)
    assert all(call[0].mutation is True for call in transport.calls)


@pytest.mark.asyncio
async def test_mutation_without_idempotency_key_fails_before_transport():
    transport = RecordingClient()
    client = OdooIntegrationClient(transport)

    with pytest.raises(ValueError, match="idempotency"):
        await client.create_result(context(), {}, "")

    assert transport.calls == []


@pytest.mark.asyncio
async def test_desired_state_read_uses_non_mutating_route():
    transport = RecordingClient()
    client = OdooIntegrationClient(transport)

    await client.read_desired_state(context(), "agent", "AGT-1")

    route, payload, kwargs = transport.calls[0]
    assert route.endpoint_key == "desired_state.read"
    assert route.mutation is False
    assert payload == {"aggregate_type": "agent", "public_id": "AGT-1"}
    assert kwargs["idempotency_key"] == ""
