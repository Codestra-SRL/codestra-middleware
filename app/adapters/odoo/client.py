"""Provider-neutral Odoo integration client built on logical endpoint keys."""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.endpoint_registry import ResolutionRequest


class ServiceClient(Protocol):
    async def request(
        self,
        route_request: ResolutionRequest,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> httpx.Response: ...


@dataclass(frozen=True)
class OdooRequestContext:
    environment: str
    organization_public_id: str
    business_unit_public_id: str
    campaign_public_id: str
    request_id: str
    correlation_id: str
    causation_id: str
    traceparent: str


class OdooIntegrationClient:
    """The sole middleware client for Odoo integration API operations."""

    def __init__(self, client: ServiceClient) -> None:
        self.client = client

    async def claim_outbox(
        self, context: OdooRequestContext, payload: dict[str, Any], idempotency_key: str
    ) -> httpx.Response:
        return await self._write("outbox.claim", context, payload, idempotency_key)

    async def renew_outbox_lease(
        self,
        context: OdooRequestContext,
        outbox_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> httpx.Response:
        return await self._write(
            "outbox.renew",
            context,
            {"outbox_id": outbox_id, **payload},
            idempotency_key,
        )

    async def acknowledge_outbox(
        self,
        context: OdooRequestContext,
        outbox_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> httpx.Response:
        return await self._write(
            "outbox.acknowledge",
            context,
            {"outbox_id": outbox_id, **payload},
            idempotency_key,
        )

    async def fail_outbox(
        self,
        context: OdooRequestContext,
        outbox_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> httpx.Response:
        return await self._write(
            "outbox.fail",
            context,
            {"outbox_id": outbox_id, **payload},
            idempotency_key,
        )

    async def release_outbox(
        self,
        context: OdooRequestContext,
        outbox_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> httpx.Response:
        return await self._write(
            "outbox.release",
            context,
            {"outbox_id": outbox_id, **payload},
            idempotency_key,
        )

    async def create_result(
        self, context: OdooRequestContext, payload: dict[str, Any], idempotency_key: str
    ) -> httpx.Response:
        return await self._write("results.create", context, payload, idempotency_key)

    async def read_desired_state(
        self,
        context: OdooRequestContext,
        aggregate_type: str,
        public_id: str,
    ) -> httpx.Response:
        return await self.client.request(
            self._route("desired_state.read", context, mutation=False),
            {"aggregate_type": aggregate_type, "public_id": public_id},
            idempotency_key="",
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
            traceparent=context.traceparent,
        )

    async def _write(
        self,
        endpoint_key: str,
        context: OdooRequestContext,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> httpx.Response:
        if not idempotency_key:
            raise ValueError("Odoo mutation requires an idempotency key")
        return await self.client.request(
            self._route(endpoint_key, context, mutation=True),
            payload,
            idempotency_key=idempotency_key,
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
            traceparent=context.traceparent,
        )

    @staticmethod
    def _route(
        endpoint_key: str, context: OdooRequestContext, *, mutation: bool
    ) -> ResolutionRequest:
        return ResolutionRequest(
            environment=context.environment,
            service_key="odoo",
            endpoint_key=endpoint_key,
            organization_public_id=context.organization_public_id,
            business_unit_public_id=context.business_unit_public_id,
            campaign_public_id=context.campaign_public_id,
            mutation=mutation,
        )
