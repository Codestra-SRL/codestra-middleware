import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.n8n_lifecycle import (
    Acknowledgement,
    ExecutionRegistration,
    FailureCallback,
    ResultCallback,
    _execution,
    acknowledge,
    park_failure,
    register_execution,
    result_callback,
)
from app.db.models import (
    EventInbox,
    IntegrationDelivery,
    IntegrationEvent,
    IntegrationResult,
    N8nExecution,
    OutboxEvent,
)


def test_canonical_runtime_database_lifecycle():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert "rehearsal" in database_url
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    asyncio.run(_scenario(database_url))


async def _scenario(database_url):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    event_id = f"event-{uuid4()}"
    correlation_id = f"correlation-{uuid4()}"
    event_key = f"idempotency-{uuid4()}"
    odoo_outbox_id = f"odoo-{uuid4()}"
    middleware_outbox_id = uuid4()
    try:
        async with factory() as db:
            await db.execute(
                text(
                    "TRUNCATE integration_trace, integration_result, "
                    "n8n_acknowledgement, n8n_execution, integration_delivery, "
                    "outbox_event, event_inbox, idempotency_record, "
                    "integration_event CASCADE"
                )
            )
            event = IntegrationEvent(
                idempotency_key=event_key,
                event_type="lead.hot",
                schema_version="1.0",
                original_event_id=event_id,
                entity_key="synthetic-lead",
                source_system="odoo",
                correlation_id=correlation_id,
                environment="staging",
                originating_odoo_outbox_id=odoo_outbox_id,
                payload_json={
                    "event_id": event_id,
                    "event_type": "lead.hot",
                    "campaign_id": "TEST_SYN",
                    "synthetic": True,
                    "references": {"business_unit_public_id": "COD"},
                    "data": {"lead_score": 95},
                },
                payload_hash="a" * 64,
                state="queued",
            )
            db.add(event)
            await db.flush()
            db.add(
                EventInbox(
                    integration_event_id=event.id,
                    event_id=event_id,
                    source="odoo",
                    event_type="lead.hot",
                    payload=event.payload_json,
                    correlation_id=correlation_id,
                )
            )
            db.add(
                OutboxEvent(
                    id=middleware_outbox_id,
                    integration_event_id=event.id,
                    topic="event.accepted",
                    payload=event.payload_json,
                    correlation_id=correlation_id,
                )
            )
            db.add(
                IntegrationDelivery(
                    event_id=event.id, target="odoo", status="disabled"
                )
            )
            await db.commit()

        registration = ExecutionRegistration(
            execution_id="execution-runtime-contract",
            event_id=event_id,
            correlation_id=correlation_id,
            idempotency_key=event_key,
            originating_odoo_outbox_id=odoo_outbox_id,
            originating_middleware_outbox_id=str(middleware_outbox_id),
            workflow_key="N8-CODESTRA-EVENT-ROUTER",
            workflow_version="1.0",
            status="RUNNING",
            details={"synthetic": True},
        )
        async with factory() as db:
            first, first_duplicate = await _execution(db, registration)
            await db.commit()
            duplicate, duplicate_seen = await _execution(db, registration)
            assert duplicate.id == first.id
            assert first_duplicate is False
            assert duplicate_seen is True
            await db.commit()
        async with factory() as db:
            with pytest.raises(HTTPException) as mismatch:
                await _execution(
                    db,
                    registration.model_copy(update={"correlation_id": "wrong"}),
                )
            assert mismatch.value.status_code == 409
            await db.rollback()
        async with factory() as db:
            with pytest.raises(HTTPException) as missing:
                await _execution(
                    db,
                    registration.model_copy(
                        update={"execution_id": "missing", "event_id": "missing"}
                    ),
                )
            assert missing.value.status_code == 422
            await db.rollback()

        concurrent = registration.model_copy(
            update={
                "execution_id": "execution-concurrent",
                "workflow_key": "N8-CONCURRENT",
            }
        )
        async with factory() as left, factory() as right:
            outcomes = await asyncio.gather(
                register_execution(concurrent, None, left),
                register_execution(concurrent, None, right),
            )
            assert sorted(item["duplicate"] for item in outcomes) == [False, True]

        async with factory() as db:
            await acknowledge(
                Acknowledgement(
                    execution_id=registration.execution_id,
                    event_id=event_id,
                    correlation_id=correlation_id,
                    status="SUCCEEDED",
                    payload={"summary": "internal-only"},
                ),
                None,
                db,
            )
            response = await result_callback(
                ResultCallback(
                    schema_version="1.0",
                    execution_id=registration.execution_id,
                    event_id=event_id,
                    correlation_id=correlation_id,
                    idempotency_key=f"result:{registration.execution_id}:{event_id}",
                    event_type="lead.hot",
                    environment="staging",
                    originating_odoo_outbox_id=odoo_outbox_id,
                    originating_middleware_outbox_id=str(middleware_outbox_id),
                    created_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                    synthetic=True,
                    terminal_status="SUCCEEDED",
                    result={"summary": "internal-only"},
                ),
                None,
                db,
            )
            assert response["accepted"] is True
            assert await db.scalar(select(IntegrationResult))
            result_outbox = await db.scalar(
                select(OutboxEvent).where(OutboxEvent.topic == "integration.result")
            )
            assert result_outbox.payload["originating_outbox_public_id"] == odoo_outbox_id
            assert result_outbox.payload["originating_middleware_outbox_id"] == str(
                middleware_outbox_id
            )

        failure_event_id = f"failure-{uuid4()}"
        failure_outbox_id = uuid4()
        async with factory() as db:
            failure_event = IntegrationEvent(
                idempotency_key=f"failure-key-{uuid4()}", event_type="lead.hot",
                schema_version="1.0", original_event_id=failure_event_id,
                entity_key="synthetic-failure", source_system="odoo",
                correlation_id=correlation_id, environment="staging",
                originating_odoo_outbox_id=failure_event_id,
                payload_json={"synthetic": True}, payload_hash="b" * 64,
                state="queued",
            )
            db.add(failure_event)
            await db.flush()
            db.add(OutboxEvent(id=failure_outbox_id, integration_event_id=failure_event.id,
                               topic="event.accepted", payload={}, correlation_id=correlation_id))
            failure_execution = N8nExecution(
                execution_id="execution-failure", event_id=failure_event_id,
                workflow_key="N8-FAILURE", workflow_version="1.0",
                correlation_id=correlation_id, status="RUNNING",
                registration_hash="c" * 64, details={},
            )
            db.add(failure_execution)
            await db.commit()
            failure = FailureCallback(
                execution_id="execution-failure", event_id=failure_event_id,
                correlation_id=correlation_id,
                idempotency_key=failure_event.idempotency_key,
                originating_odoo_outbox_id=failure_event_id,
                originating_middleware_outbox_id=str(failure_outbox_id),
                environment="staging", synthetic=True, attempt=5,
                error_code="retry_exhausted", error_summary="bounded failure",
            )
            parked = await park_failure(failure, None, db)
            assert parked == {"accepted": True, "duplicate": False, "status": "DEAD_LETTERED"}
            duplicate = await park_failure(failure, None, db)
            assert duplicate["duplicate"] is True
    finally:
        await engine.dispose()
