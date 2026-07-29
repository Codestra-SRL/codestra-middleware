import pytest

from app.adapters.odoo.telephony import (
    OdooConvergenceError,
    deliver_telephony_result_and_verify,
)


class FakeValidatedOdoo:
    def __init__(self, *, drift: bool = False):
        self.calls: list[tuple[str, dict, dict]] = []
        self.drift = drift

    async def validated_request(self, operation, payload, **kwargs):
        self.calls.append((operation, payload, kwargs))
        common = {
            "integration_uuid": "INT-SYNTHETIC-001",
            "target_public_id": "EPT-SYNTHETIC-001",
            "correlation_id": "COR-SYNTHETIC-001",
        }
        if operation == "results.create":
            return {**common, "delivery_public_id": "DEL-SYNTHETIC-001"}
        if operation == "results.read":
            return {**common, "result_hash": "sha256:" + "a" * 64}
        if operation in {"desired_state.read", "telephony.projections.read"}:
            return {**common, "desired_state_version": 3}
        if operation == "reconciliation.drifts.read":
            return {
                **common,
                "material_drift": self.drift,
                "unresolved_count": int(self.drift),
            }
        return common


def result():
    return {
        "result_public_id": "RES-SYNTHETIC-001",
        "integration_uuid": "INT-SYNTHETIC-001",
        "target_public_id": "EPT-SYNTHETIC-001",
        "observed_state_version": 3,
        "result_hash": "sha256:" + "a" * 64,
    }


@pytest.mark.asyncio
async def test_terminal_result_callback_reads_every_projection_before_convergence():
    client = FakeValidatedOdoo()
    observed = await deliver_telephony_result_and_verify(
        client,
        result(),
        idempotency_key="test-test-test",
        request_id="REQ-SYNTHETIC-001",
        correlation_id="COR-SYNTHETIC-001",
        causation_id="CAU-SYNTHETIC-001",
        traceparent="00-" + "1" * 32 + "-" + "2" * 16 + "-01",
    )
    assert observed["converged"] is True
    assert [call[0] for call in client.calls] == [
        "results.create",
        "results.read",
        "results.by_delivery",
        "desired_state.read",
        "telephony.projections.read",
        "telephony.mappings.read",
        "traces.read",
        "reconciliation.drifts.read",
    ]
    assert {call[2]["idempotency_key"] for call in client.calls} == {
        "test-test-test"
    }


@pytest.mark.asyncio
async def test_unresolved_odoo_drift_blocks_cross_system_convergence():
    with pytest.raises(OdooConvergenceError, match="unresolved telephony drift"):
        await deliver_telephony_result_and_verify(
            FakeValidatedOdoo(drift=True),
            result(),
            idempotency_key="test-test-test",
            request_id="REQ-SYNTHETIC-001",
            correlation_id="COR-SYNTHETIC-001",
            causation_id="CAU-SYNTHETIC-001",
            traceparent="00-" + "1" * 32 + "-" + "2" * 16 + "-01",
        )
