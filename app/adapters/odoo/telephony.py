"""Odoo PR #9 telephony callback and convergence orchestration."""

from __future__ import annotations

from typing import Any, Protocol


class ValidatedOdooClient(Protocol):
    async def validated_request(
        self, operation: str, payload: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]: ...


class OdooConvergenceError(RuntimeError):
    pass


async def deliver_telephony_result_and_verify(
    client: ValidatedOdooClient,
    result: dict[str, Any],
    *,
    idempotency_key: str,
    request_id: str,
    correlation_id: str,
    causation_id: str,
    traceparent: str,
) -> dict[str, Any]:
    """Persist a terminal result and prove every Odoo projection converged.

    All calls use the same durable identity and trace.  The caller must not
    mark the middleware operation reconciled until this function returns.
    """
    call = {
        "idempotency_key": idempotency_key,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "traceparent": traceparent,
    }
    accepted = await client.validated_request("results.create", result, **call)
    delivery_id = accepted.get("delivery_public_id") or result.get("delivery_public_id")
    query = {
        "result_public_id": result["result_public_id"],
        "delivery_public_id": delivery_id,
        "integration_uuid": result["integration_uuid"],
        "target_public_id": result["target_public_id"],
    }
    views: dict[str, dict[str, Any]] = {}
    for operation in (
        "results.read",
        "results.by_delivery",
        "desired_state.read",
        "telephony.projections.read",
        "telephony.mappings.read",
        "traces.read",
        "reconciliation.drifts.read",
    ):
        views[operation] = await client.validated_request(operation, query, **call)

    expected = {
        "integration_uuid": result["integration_uuid"],
        "target_public_id": result["target_public_id"],
        "correlation_id": correlation_id,
    }
    for operation, view in views.items():
        for key, value in expected.items():
            observed = view.get(key)
            if observed is not None and observed != value:
                raise OdooConvergenceError(f"{operation} {key} binding mismatch")
    desired_version = result["observed_state_version"]
    for operation in ("desired_state.read", "telephony.projections.read"):
        if views[operation].get("desired_state_version") != desired_version:
            raise OdooConvergenceError(f"{operation} state version mismatch")
    if views["telephony.mappings.read"].get("target_public_id") != result[
        "target_public_id"
    ]:
        raise OdooConvergenceError("Odoo target mapping does not converge")
    if views["results.read"].get("result_hash") != result["result_hash"]:
        raise OdooConvergenceError("Odoo result readback hash mismatch")
    drift = views["reconciliation.drifts.read"]
    if drift.get("material_drift") is True or drift.get("unresolved_count", 0) != 0:
        raise OdooConvergenceError("Odoo reports unresolved telephony drift")
    return {"accepted": accepted, "readback": views, "converged": True}
