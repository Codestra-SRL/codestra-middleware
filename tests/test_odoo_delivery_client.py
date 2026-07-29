from types import SimpleNamespace

import pytest

from app.adapters.odoo.client import OdooDeliveryClient


class FakeServiceClient:
    def __init__(self):
        self.calls = []

    async def request(self, route, payload, **kwargs):
        self.calls.append((route, payload, kwargs))
        return SimpleNamespace(status_code=201)


@pytest.mark.asyncio
async def test_odoo_client_resolves_logical_endpoint_and_keeps_idempotency():
    transport = FakeServiceClient()
    client = OdooDeliveryClient(transport, "staging", "ORG", "BU", "CMP")
    response = await client.request(
        "results.create",
        {"result_public_id": "R-1"},
        idempotency_key="IDM-1",
        request_id="REQ-1",
        correlation_id="COR-1",
        causation_id="CAU-1",
        traceparent="00-" + "1" * 32 + "-" + "2" * 16 + "-01",
    )
    assert response.status_code == 201
    route, payload, kwargs = transport.calls[0]
    assert route.service_key == "odoo"
    assert route.endpoint_key == "odoo.results.create"
    assert route.business_unit_public_id == "BU"
    assert kwargs["idempotency_key"] == "IDM-1"
    assert payload["result_public_id"] == "R-1"


@pytest.mark.asyncio
async def test_unknown_operation_fails_closed():
    client = OdooDeliveryClient(FakeServiceClient(), "staging", "ORG")
    with pytest.raises(RuntimeError, match="unknown Odoo endpoint"):
        await client.request(
            "unsupported",
            {},
            idempotency_key="IDM",
            request_id="REQ",
            correlation_id="COR",
            causation_id="CAU",
            traceparent="00-" + "1" * 32 + "-" + "2" * 16 + "-01",
        )
