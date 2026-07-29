"""Registry-backed Odoo delivery client.

This adapter owns Odoo endpoint contracts only; URL, credential, TLS, retry,
and idempotency policy remain owned by the common service client and registry.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.endpoint_registry import ResolutionRequest, ResolvedEndpoint
from app.core.service_client import CommonServiceClient
from app.core.telephony_commands import payload_hash

ODOO_SERVICE_KEY = "odoo"
ODOO_ENDPOINTS = {
    "outbox.claim": "odoo.outbox.claim",
    "outbox.read": "odoo.outbox.read",
    "outbox.renew": "odoo.outbox.renew",
    "outbox.acknowledge": "odoo.outbox.acknowledge",
    "outbox.fail": "odoo.outbox.fail",
    "outbox.release": "odoo.outbox.release",
    "results.create": "odoo.results.create",
    "results.read": "odoo.results.read",
    "results.by_delivery": "odoo.results.by_delivery",
    "desired_state.read": "odoo.desired_state.read",
    "agents.read": "odoo.agents.read",
    "leads.read": "odoo.leads.read",
    "campaigns.read": "odoo.campaigns.read",
    "traces.read": "odoo.traces.read",
    "telephony.projections.read": "odoo.telephony.projections.read",
    "telephony.mappings.read": "odoo.telephony.mappings.read",
    "reconciliation.runs.read": "odoo.reconciliation.runs.read",
    "reconciliation.drifts.read": "odoo.reconciliation.drifts.read",
}

ODOO_READ_OPERATIONS = frozenset(
    {
        "outbox.read",
        "results.read",
        "results.by_delivery",
        "desired_state.read",
        "agents.read",
        "leads.read",
        "campaigns.read",
        "traces.read",
        "telephony.projections.read",
        "telephony.mappings.read",
        "reconciliation.runs.read",
        "reconciliation.drifts.read",
    }
)


class OdooDeliveryError(RuntimeError):
    pass


class OdooTargetAttestor(Protocol):
    async def attest(
        self,
        *,
        route: ResolvedEndpoint,
        environment: str,
        endpoint_key: str,
        configuration_checksum: str,
        correlation_id: str,
    ) -> bool: ...


@dataclass(frozen=True)
class OdooDeliveryClient:
    service_client: CommonServiceClient
    environment: str
    organization_public_id: str
    business_unit_public_id: str = ""
    campaign_public_id: str = ""
    attestor: OdooTargetAttestor | None = None

    async def aclose(self) -> None:
        await self.service_client.aclose()

    async def request(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        request_id: str,
        correlation_id: str,
        causation_id: str,
        traceparent: str,
        tracestate: str = "",
    ) -> httpx.Response:
        endpoint_key = ODOO_ENDPOINTS.get(operation)
        if endpoint_key is None:
            raise OdooDeliveryError("unknown Odoo endpoint operation")
        route = ResolutionRequest(
            environment=self.environment,
            service_key=ODOO_SERVICE_KEY,
            endpoint_key=endpoint_key,
            api_version="v1",
            organization_public_id=self.organization_public_id,
            business_unit_public_id=self.business_unit_public_id,
            campaign_public_id=self.campaign_public_id,
            mutation=operation not in ODOO_READ_OPERATIONS,
        )
        return await self.service_client.request(
            route,
            payload,
            idempotency_key=idempotency_key,
            request_id=request_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            traceparent=traceparent,
            tracestate=tracestate,
        )

    async def validated_request(
        self,
        operation: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
        request_id: str,
        correlation_id: str,
        causation_id: str,
        traceparent: str,
        tracestate: str = "",
    ) -> dict[str, Any]:
        """Call an Odoo PR #9 route with attestation and response-hash binding."""
        endpoint_key = ODOO_ENDPOINTS.get(operation)
        if endpoint_key is None:
            raise OdooDeliveryError("unknown Odoo endpoint operation")
        route_request = ResolutionRequest(
            environment=self.environment,
            service_key=ODOO_SERVICE_KEY,
            endpoint_key=endpoint_key,
            api_version="v1",
            organization_public_id=self.organization_public_id,
            business_unit_public_id=self.business_unit_public_id,
            campaign_public_id=self.campaign_public_id,
            mutation=operation not in ODOO_READ_OPERATIONS,
        )
        route = await self.service_client.resolver.resolve(route_request)
        if not route.target_attestation_required or self.attestor is None:
            raise OdooDeliveryError("Odoo target attestation is required")
        if not await self.attestor.attest(
            route=route,
            environment=self.environment,
            endpoint_key=endpoint_key,
            configuration_checksum=route.configuration_checksum,
            correlation_id=correlation_id,
        ):
            raise OdooDeliveryError("Odoo target attestation failed")
        response = await self.service_client.request_resolved(
            route,
            payload,
            idempotency_key=idempotency_key,
            request_id=request_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            traceparent=traceparent,
            tracestate=tracestate,
        )
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError as exc:
            raise OdooDeliveryError("Odoo response is invalid") from exc
        if not isinstance(result, dict):
            raise OdooDeliveryError("Odoo response schema is invalid")
        response_hash = result.get("response_hash")
        canonical = {key: value for key, value in result.items() if key != "response_hash"}
        if response_hash != f"sha256:{payload_hash(canonical)}":
            raise OdooDeliveryError("Odoo response hash mismatch")
        return result
