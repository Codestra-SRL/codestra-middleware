"""Fail-closed durable delivery of acknowledged n8n results to Odoo."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automation import canonical_hash
from app.core.config import settings
from app.core.endpoint_registry import (
    RegistryResolver,
    ResolutionRequest,
    SignedSnapshotCache,
    SqlEndpointRepository,
)
from app.core.service_client import CommonServiceClient
from app.core.token_manager import TokenManager
from app.db.models import (
    BroadEventDelivery,
    IntegrationEvent,
    N8nAcknowledgement,
    N8nExecutionRegistration,
    OdooResultDelivery,
)


class OdooResultError(RuntimeError):
    pass


class OdooServiceClient(Protocol):
    async def request(
        self,
        route_request: ResolutionRequest,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> httpx.Response: ...

    async def aclose(self) -> None: ...


async def deliver_result(
    session: AsyncSession,
    result_delivery_id: UUID,
    *,
    client: OdooServiceClient | None = None,
) -> dict[str, Any]:
    if not settings.odoo_result_delivery_enabled:
        raise OdooResultError("Odoo result delivery is disabled")
    result = await session.get(
        OdooResultDelivery, result_delivery_id, with_for_update=True
    )
    if result is None or result.status not in {"PENDING", "RETRY"}:
        raise OdooResultError("result delivery is not claimable")
    acknowledgement = await session.get(N8nAcknowledgement, result.acknowledgement_id)
    registration = (
        await session.scalar(
            select(N8nExecutionRegistration).where(
                N8nExecutionRegistration.registration_id
                == acknowledgement.registration_id
            )
        )
        if acknowledgement
        else None
    )
    delivery = (
        await session.get(BroadEventDelivery, acknowledgement.delivery_id)
        if acknowledgement
        else None
    )
    event = await session.get(IntegrationEvent, delivery.event_id) if delivery else None
    if (
        acknowledgement is None
        or registration is None
        or delivery is None
        or event is None
    ):
        raise OdooResultError("result source binding is incomplete")
    result.status = "RESERVED"
    result.reserved_at = datetime.now(UTC)
    await session.commit()
    payload = event.payload_json
    body: dict[str, Any] = {
        "schema_version": "1.0",
        "result_public_id": str(result.result_public_id),
        "delivery_id": str(delivery.delivery_id),
        "event_id": acknowledgement.event_id,
        "registration_id": str(registration.registration_id),
        "acknowledgement_id": str(acknowledgement.acknowledgement_id),
        "correlation_id": acknowledgement.correlation_id,
        "workflow_id": acknowledgement.workflow_id,
        "workflow_version": acknowledgement.workflow_version,
        "execution_id": acknowledgement.execution_id,
        "execution_status": acknowledgement.execution_status,
        "result_classification": acknowledgement.result_classification,
        "result_hash": f"sha256:{acknowledgement.result_hash}",
        "originating_outbox_public_id": result.originating_outbox_public_id,
        "organization_public_id": str(payload.get("organization_public_id", "")),
        "business_unit_public_id": str(payload.get("business_unit_public_id", "")),
        "campaign_public_id": str(payload.get("campaign_public_id", "")),
        "source_system": "codestra-middleware",
        "source_environment": settings.environment,
        "policy_hash": f"sha256:{acknowledgement.policy_hash}",
        "acknowledged_at": acknowledgement.persisted_at.isoformat(),
        "reconciliation_status": "RECONCILED",
        "payload": {"summary": "internal reconciliation completed"},
    }
    owns_client = client is None
    service_client = client or _build_service_client(session)
    try:
        response = await service_client.request(
            ResolutionRequest(
                environment=settings.environment,
                service_key="odoo",
                endpoint_key="results.create",
                organization_public_id=body["organization_public_id"],
                business_unit_public_id=body["business_unit_public_id"],
                campaign_public_id=body["campaign_public_id"],
                mutation=True,
            ),
            body,
            idempotency_key=str(result.result_public_id),
            request_id=f"REQ-{uuid4()}",
            correlation_id=acknowledgement.correlation_id,
            causation_id=str(acknowledgement.acknowledgement_id),
            traceparent=_traceparent(
                acknowledgement.correlation_id,
                str(result.result_public_id),
            ),
        )
    finally:
        if owns_client:
            await service_client.aclose()
    result = await session.get(
        OdooResultDelivery, result_delivery_id, with_for_update=True
    )
    if result is None:
        raise OdooResultError("result reservation disappeared")
    if response.is_redirect:
        result.status = "DEAD_LETTER"
        result.last_error_class = "REDIRECT_REJECTED"
        await session.commit()
        raise OdooResultError("Odoo redirect rejected")
    if response.status_code not in {200, 201}:
        result.attempts += 1
        if response.status_code in {401, 403, 409, 422} or result.attempts >= 3:
            result.status = "DEAD_LETTER"
        else:
            result.status = "RETRY"
            result.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=5 * 2 ** (result.attempts - 1)
            )
        result.last_error_class = f"HTTP_{response.status_code}"
        await session.commit()
        raise OdooResultError("Odoo result rejected")
    try:
        accepted = response.json()
    except ValueError as exc:
        raise OdooResultError("Odoo response is invalid") from exc
    required = {
        "persisted": True,
        "result_public_id": str(result.result_public_id),
        "originating_outbox_public_id": result.originating_outbox_public_id,
        "integration_status": "COMPLETED",
    }
    if any(accepted.get(key) != value for key, value in required.items()):
        raise OdooResultError("Odoo response binding mismatch")
    response_without_hash = {
        key: value for key, value in accepted.items() if key != "response_hash"
    }
    expected_hash = f"sha256:{canonical_hash(response_without_hash)}"
    if accepted.get("response_hash") != expected_hash:
        raise OdooResultError("Odoo response hash mismatch")
    result.status = "DELIVERED"
    result.delivered_at = datetime.now(UTC)
    result.odoo_result_inbox_id = str(accepted["result_inbox_id"])
    result.response_hash = expected_hash.removeprefix("sha256:")
    await session.commit()
    return accepted


def _traceparent(correlation_id: str, result_public_id: str) -> str:
    trace_id = canonical_hash({"correlation_id": correlation_id})[:32]
    span_id = canonical_hash({"result_public_id": result_public_id})[:16]
    return f"00-{trace_id}-{span_id}-01"


def _build_service_client(session: AsyncSession) -> CommonServiceClient:
    async def load_private_key(reference: str) -> str:
        if reference != settings.odoo_service_credential_reference:
            raise OdooResultError("Odoo credential reference is not approved")
        path = Path(settings.odoo_service_private_key_file)
        if not path.is_absolute() or not path.is_file():
            raise OdooResultError("Odoo service private key is unavailable")
        return path.read_text()

    cache = SignedSnapshotCache(
        Redis.from_url(settings.redis_url, decode_responses=True),
        settings.load_registry_snapshot_key(),
        l1_ttl_seconds=settings.registry_l1_ttl_seconds,
        l2_ttl_seconds=settings.registry_l2_ttl_seconds,
        stale_grace_seconds=settings.registry_stale_grace_seconds,
    )
    return CommonServiceClient(
        RegistryResolver(SqlEndpointRepository(session), cache),
        TokenManager(settings.odoo_results_client_id, load_private_key),
        token_endpoint_key=ResolutionRequest(
            environment=settings.environment,
            service_key="identity",
            endpoint_key="oauth.token",
        ),
    )


async def claim_result_delivery(session: AsyncSession) -> OdooResultDelivery | None:
    result = await session.scalar(
        select(OdooResultDelivery)
        .where(
            OdooResultDelivery.status.in_({"PENDING", "RETRY"}),
            (OdooResultDelivery.next_attempt_at.is_(None))
            | (OdooResultDelivery.next_attempt_at <= datetime.now(UTC)),
        )
        .order_by(OdooResultDelivery.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    return result
