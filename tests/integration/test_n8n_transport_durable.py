import asyncio
import json
import os
import time
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api.v1.n8n_transport import acknowledge_execution, register_execution
from app.core.automation import canonical_hash, sign_exact_body
from app.core.config import settings
from app.db.models import BroadEventDelivery, IntegrationEvent, OutboxEvent


def request_for(body: bytes) -> Request:
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/"}, receive)


def test_durable_registration_acknowledgement_and_odoo_result(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert "diag" in database_url or "rehearsal" in database_url
    monkeypatch.setattr(settings, "webhook_shared_secret", "synthetic-test-secret")

    async def scenario():
        engine = create_async_engine(database_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        event_public_id = f"n8n-transport-test-{uuid4()}"
        correlation_id = f"correlation-{uuid4()}"
        payload = {"operation": "reconciliation.run", "synthetic": True}
        payload_hash = canonical_hash(payload)
        policy_hash = "a" * 64
        workflow_id = "n8n-test-assigned-id"
        workflow_version = "test-version-1"
        async with session_factory() as session:
            event = IntegrationEvent(
                idempotency_key=event_public_id,
                event_type="reconciliation.run",
                schema_version="1.0",
                original_event_id=event_public_id,
                source_system="odoo",
                correlation_id=correlation_id,
                payload_json=payload,
                payload_hash=payload_hash,
                state="queued",
            )
            session.add(event)
            await session.flush()
            delivery = BroadEventDelivery(
                event_id=event.id,
                workflow_id=workflow_id,
                workflow_version=workflow_version,
                idempotency_key=event_public_id,
                target_identity="n8n-production-test",
                target_environment="production",
                payload_hash=payload_hash,
                policy_hash=policy_hash,
                attempt_number=1,
                status="SUBMITTED",
                reserved_at=datetime.now(UTC),
                submitted_at=datetime.now(UTC),
            )
            session.add(delivery)
            await session.commit()

            execution_id = f"execution-{uuid4()}"
            registration = {
                "schema_version": "1.0",
                "delivery_id": str(delivery.delivery_id),
                "event_id": event_public_id,
                "workflow_id": workflow_id,
                "workflow_version": workflow_version,
                "execution_id": execution_id,
                "payload_hash": payload_hash,
                "environment": "production",
                "accepted_at": datetime.now(UTC).isoformat(),
            }
            raw_registration = json.dumps(registration).encode()
            timestamp = str(int(time.time()))
            response = await register_execution(
                request_for(raw_registration),
                timestamp,
                uuid4().hex,
                "codestra-n8n-production",
                sign_exact_body(raw_registration, settings.webhook_shared_secret),
                session,
            )
            assert response["idempotency_status"] == "created"

            acknowledgement_id = uuid4()
            acknowledgement = {
                "schema_version": "1.0",
                "acknowledgement_id": str(acknowledgement_id),
                "delivery_id": str(delivery.delivery_id),
                "event_id": event_public_id,
                "workflow_id": workflow_id,
                "workflow_version": workflow_version,
                "execution_id": execution_id,
                "execution_status": "SUCCEEDED",
                "result_classification": "INTERNAL_RECONCILIATION_COMPLETE",
                "result_hash": "b" * 64,
                "started_at": datetime.now(UTC).isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
                "attempt_number": 1,
                "correlation_id": correlation_id,
                "policy_hash": policy_hash,
            }
            raw_ack = json.dumps(acknowledgement).encode()
            persisted = await acknowledge_execution(
                request_for(raw_ack),
                timestamp,
                uuid4().hex,
                "codestra-n8n-production",
                sign_exact_body(raw_ack, settings.webhook_shared_secret),
                session,
            )
            assert persisted["persisted"] is True
            duplicate = await acknowledge_execution(
                request_for(raw_ack),
                timestamp,
                uuid4().hex,
                "codestra-n8n-production",
                sign_exact_body(raw_ack, settings.webhook_shared_secret),
                session,
            )
            assert duplicate["persisted"] is True
            delivery_status = await session.scalar(
                select(BroadEventDelivery.status).where(
                    BroadEventDelivery.delivery_id == delivery.delivery_id
                )
            )
            assert delivery_status == "ACKNOWLEDGED"
            result_count = await session.scalar(
                select(text("count(*)"))
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.topic == "odoo.integration.result",
                    OutboxEvent.correlation_id == correlation_id,
                )
            )
            assert result_count == 1
        await engine.dispose()

    asyncio.run(scenario())
