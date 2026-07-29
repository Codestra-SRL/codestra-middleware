"""Fail-closed durable delivery of acknowledged n8n results to Odoo."""

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automation import canonical_hash
from app.core.config import settings
from app.core.service_tokens import client_credentials_token
from app.db.models import (
    BroadEventDelivery,
    IntegrationEvent,
    N8nAcknowledgement,
    N8nExecutionRegistration,
    OdooResultDelivery,
)


class OdooResultError(RuntimeError):
    pass


async def deliver_result(
    session: AsyncSession,
    result_delivery_id: UUID,
    *,
    client: httpx.AsyncClient | None = None,
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
    body = {
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
        "source_environment": "production",
        "policy_hash": f"sha256:{acknowledgement.policy_hash}",
        "acknowledged_at": acknowledgement.persisted_at.isoformat(),
        "reconciliation_status": "RECONCILED",
        "payload": {"summary": "internal reconciliation completed"},
    }
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    owns_client = client is None
    http = client or httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(10),
        verify=settings.odoo_results_ca_file or True,
    )
    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=10) as token_http:
            token = await client_credentials_token(
                token_url=settings.odoo_results_token_url,
                client_id=settings.odoo_results_client_id,
                client_secret_file=settings.odoo_results_client_secret_file,
                audience=settings.odoo_results_audience,
                scope=settings.odoo_results_scope,
                client=token_http,
            )
        response = await http.post(
            settings.odoo_results_url,
            content=encoded,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Idempotency-Key": str(result.result_public_id),
                "X-Codestra-Timestamp": str(int(time.time())),
                "X-Codestra-Nonce": uuid4().hex,
                "X-Codestra-Body-SHA256": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
                "X-Codestra-Correlation-ID": acknowledgement.correlation_id,
            },
        )
    finally:
        if owns_client:
            await http.aclose()
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
