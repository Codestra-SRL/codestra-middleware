import asyncio
import os
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
            replay = await create_command(command, idempotency_key, session)
            assert first["state"] == "AUTHORIZED"
            assert replay["replayed"] is True
            assert replay["command_id"] == first["command_id"]
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
    finally:
        await engine.dispose()
