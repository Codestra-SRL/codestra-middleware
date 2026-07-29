import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.commands import create_command
from app.core.telephony_commands import (
    TelephonyCommandRequest,
    payload_hash,
)
from app.db.models import PolicyDecision, TelephonyCommandJournal
from app.workers.telephony_commands import claim_authorized, dispatch_one


def test_command_policy_and_idempotency_are_database_authoritative():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert "rehearsal" in database_url or "diag" in database_url
    asyncio.run(_scenario(database_url))


async def _scenario(database_url: str):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    correlation_id = f"COR-SYNTHETIC-{uuid4()}"
    idempotency_key = f"IDM-SYNTHETIC-{uuid4()}"
    decision_id = uuid4()
    context = {
        "decision_id": str(decision_id),
        "correlation_id": correlation_id,
        "allow": True,
        "enforced": True,
        "action": "sync",
        "resource": "telephony.endpoint",
        "expiration": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        "authorization_scope": {
            "action": "sync",
            "subject": "AGT-SYNTHETIC-DB",
            "resource": "telephony.asterisk.endpoint.apply",
            "environment": "staging",
            "business_unit": "BU-SYNTHETIC-DB",
            "campaign": "CMP-SYNTHETIC-DB",
            "agent": "AGT-SYNTHETIC-DB",
        },
    }
    command = TelephonyCommandRequest.model_validate(
        {
            "schema_version": "1.0",
            "command_type": "telephony.asterisk.endpoint.apply",
            "aggregate_type": "agent",
            "aggregate_public_id": "AGT-SYNTHETIC-DB",
            "aggregate_version": 1,
            "environment": "staging",
            "business_unit_public_id": "BU-SYNTHETIC-DB",
            "campaign_public_id": "CMP-SYNTHETIC-DB",
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
            "causation_id": "CAU-SYNTHETIC-DB",
            "policy_decision_id": str(decision_id),
            "policy_decision_hash": payload_hash(context),
            "payload": {
                "endpoint_public_id": "EPT-SYNTHETIC-DB",
                "agent_public_id": "AGT-SYNTHETIC-DB",
                "allocation_reservation_id": "RSV-SYNTHETIC-DB",
                "desired_state_version": 1,
            },
        }
    )
    try:
        async with factory() as session:
            session.add(
                PolicyDecision(
                    id=decision_id,
                    policy="synthetic-telephony-policy",
                    allowed=True,
                    reason="allowed",
                    correlation_id=correlation_id,
                    context=context,
                )
            )
            await session.commit()
            first = await create_command(command, idempotency_key, session)
            stored_decision = await session.get(PolicyDecision, decision_id)
            assert stored_decision is not None
            stored_decision.context = {
                **context,
                "expiration": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            }
            await session.commit()
            replay = await create_command(command, idempotency_key, session)
            assert first["state"] == "AUTHORIZED"
            assert replay["replayed"] is True
            assert replay["command_id"] == first["command_id"]
            stored_decision.context = context
            await session.commit()
            stored = await session.scalar(
                select(TelephonyCommandJournal).where(
                    TelephonyCommandJournal.correlation_id == correlation_id
                )
            )
            assert stored is not None
            assert stored.command_id == UUID(first["command_id"])

            changed = command.model_copy(update={"aggregate_version": 2})
            with pytest.raises(HTTPException) as conflict:
                await create_command(changed, idempotency_key, session)
            assert conflict.value.status_code == 409

            wrong_scope = command.model_copy(
                update={
                    "idempotency_key": f"IDM-SYNTHETIC-{uuid4()}",
                    "campaign_public_id": "CMP-SYNTHETIC-OTHER",
                }
            )
            with pytest.raises(HTTPException, match="authorization scope mismatch"):
                await create_command(
                    wrong_scope, wrong_scope.idempotency_key, session
                )

            expired_id = uuid4()
            expired_context = {
                **context,
                "decision_id": str(expired_id),
                "expiration": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
            }
            session.add(
                PolicyDecision(
                    id=expired_id,
                    policy="synthetic-telephony-policy",
                    allowed=True,
                    reason="allowed",
                    correlation_id=correlation_id,
                    context=expired_context,
                )
            )
            await session.commit()
            expired = command.model_copy(
                update={
                    "idempotency_key": f"IDM-SYNTHETIC-{uuid4()}",
                    "policy_decision_id": str(expired_id),
                    "policy_decision_hash": payload_hash(expired_context),
                }
            )
            with pytest.raises(HTTPException, match="policy decision expired"):
                await create_command(expired, expired.idempotency_key, session)
            assert (
                await claim_authorized(session, environment="production")
                is None
            )
            stored.state = "SUBMITTING"
            stored.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

        class SyntheticClient:
            competing_claim = None

            async def dispatch(self, command_id, value, *, traceparent):
                assert value.idempotency_key == idempotency_key
                assert traceparent.startswith("00-")
                return {
                    "operation_id": str(uuid4()),
                    "endpoint_key": "telephony.asterisk.endpoints.apply",
                    "readback_endpoint_key": "telephony.asterisk.endpoints.read",
                    "target_configuration_checksum": "sha256:" + "a" * 64,
                    "target_attested": True,
                    "desired_hash": payload_hash(value.desired_state()),
                }

            async def readback(self, value, operation, *, traceparent):
                async with factory() as competing_session:
                    self.competing_claim = await claim_authorized(
                        competing_session, environment="staging"
                    )
                return {
                    "actual": {"desired_state": value.desired_state()},
                    "actual_hash": operation["desired_hash"],
                    "readback_matches": True,
                }

        client = SyntheticClient()
        worker_result = await dispatch_one(
            factory,
            lambda: client,
            environment="staging",
            traceparent_factory=lambda: "00-" + "1" * 32 + "-" + "2" * 16 + "-01",
        )
        assert worker_result["state"] == "SUCCEEDED"
        assert client.competing_claim is None
        async with factory() as session:
            stored = await session.scalar(
                select(TelephonyCommandJournal).where(
                    TelephonyCommandJournal.correlation_id == correlation_id
                )
            )
            assert stored is not None
            assert stored.state == "SUCCEEDED"

            next_command = command.model_copy(
                update={
                    "aggregate_version": 2,
                    "idempotency_key": f"IDM-SYNTHETIC-{uuid4()}",
                }
            )
            accepted_next = await create_command(
                next_command, next_command.idempotency_key, session
            )
            assert accepted_next["aggregate_version"] == 2

            duplicate_version = command.model_copy(
                update={
                    "aggregate_version": 2,
                    "idempotency_key": f"IDM-SYNTHETIC-{uuid4()}",
                }
            )
            with pytest.raises(
                HTTPException, match="stale or duplicate aggregate version"
            ):
                await create_command(
                    duplicate_version, duplicate_version.idempotency_key, session
                )

            stale_version = command.model_copy(
                update={"idempotency_key": f"IDM-SYNTHETIC-{uuid4()}"}
            )
            with pytest.raises(
                HTTPException, match="stale or duplicate aggregate version"
            ):
                await create_command(
                    stale_version, stale_version.idempotency_key, session
                )
    finally:
        await engine.dispose()
