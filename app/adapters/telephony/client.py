"""Registry-only telephony command dispatcher."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.core.endpoint_registry import ResolutionRequest
from app.core.service_client import CommonServiceClient
from app.core.telephony_commands import (
    MUTATION_ENDPOINTS,
    READBACK_ENDPOINTS,
    TelephonyCommandRequest,
    normalized_actual_state,
    payload_hash,
)


class TelephonyClientError(RuntimeError):
    pass


class TargetAttestor(Protocol):
    async def attest(
        self, *, endpoint_key: str, configuration_checksum: str, correlation_id: str
    ) -> bool: ...


class TelephonyServiceClient:
    def __init__(
        self, common_client: CommonServiceClient, attestor: TargetAttestor
    ) -> None:
        self.common_client = common_client
        self.attestor = attestor

    def _route(
        self, command: TelephonyCommandRequest, endpoint_key: str, *, mutation: bool
    ) -> ResolutionRequest:
        return ResolutionRequest(
            environment=command.environment,
            service_key="telephony-adapter",
            endpoint_key=endpoint_key,
            business_unit_public_id=command.business_unit_public_id,
            campaign_public_id=command.campaign_public_id,
            mutation=mutation,
        )

    async def dispatch(
        self, command_id: str, command: TelephonyCommandRequest, *, traceparent: str
    ) -> dict[str, Any]:
        endpoint_key = MUTATION_ENDPOINTS[command.command_type]
        route_request = self._route(command, endpoint_key, mutation=True)
        route = await self.common_client.resolver.resolve(route_request)
        if not route.target_attestation_required:
            raise TelephonyClientError("telephony mutation route must require attestation")
        if not await self.attestor.attest(
            endpoint_key=endpoint_key,
            configuration_checksum=route.configuration_checksum,
            correlation_id=command.correlation_id,
        ):
            raise TelephonyClientError("telephony target attestation failed")
        response = await self.common_client.request_resolved(
            route,
            {
                "command_id": command_id,
                **command.model_dump(mode="json"),
            },
            idempotency_key=command.idempotency_key,
            request_id=command_id,
            correlation_id=command.correlation_id,
            causation_id=command.causation_id,
            traceparent=traceparent,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or not result.get("operation_id"):
            raise TelephonyClientError("invalid telephony operation acknowledgement")
        try:
            operation_id = str(UUID(str(result["operation_id"])))
        except ValueError:
            raise TelephonyClientError("telephony operation ID must be a UUID") from None
        return {
            "operation_id": operation_id,
            "endpoint_key": endpoint_key,
            "readback_endpoint_key": READBACK_ENDPOINTS[command.command_type],
            "target_configuration_checksum": route.configuration_checksum,
            "target_attested": True,
            "desired_hash": payload_hash(
                command.desired_state()
            ),
        }

    async def readback(
        self,
        command: TelephonyCommandRequest,
        operation: dict[str, Any],
        *,
        traceparent: str,
    ) -> dict[str, Any]:
        endpoint_key = READBACK_ENDPOINTS[command.command_type]
        response = await self.common_client.request(
            self._route(command, endpoint_key, mutation=False),
            {
                "operation_id": operation["operation_id"],
                "aggregate_public_id": command.aggregate_public_id,
                "allocation_reservation_id": command.payload.allocation_reservation_id,
            },
            idempotency_key=command.idempotency_key,
            request_id=str(operation["operation_id"]),
            correlation_id=command.correlation_id,
            causation_id=command.causation_id,
            traceparent=traceparent,
        )
        response.raise_for_status()
        actual = response.json()
        if not isinstance(actual, dict):
            raise TelephonyClientError("invalid telephony readback")
        try:
            normalized = normalized_actual_state(command, actual)
        except ValueError as exc:
            raise TelephonyClientError(str(exc)) from exc
        actual_hash = payload_hash(normalized)
        return {
            "actual": actual,
            "normalized_actual": normalized,
            "actual_hash": actual_hash,
            "readback_matches": actual_hash == operation["desired_hash"],
        }
