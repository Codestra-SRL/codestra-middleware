"""Durable claim/dispatch/readback/finalize telephony command worker."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.telephony_commands import (
    TelephonyCommandRequest,
    TelephonyCommandState,
)
from app.db.models import TelephonyCommandJournal, TelephonyOperationJournal


class TelephonyDispatcher(Protocol):
    async def dispatch(
        self, command_id: str, command: TelephonyCommandRequest, *, traceparent: str
    ) -> dict[str, Any]: ...

    async def readback(
        self,
        command: TelephonyCommandRequest,
        operation: dict[str, Any],
        *,
        traceparent: str,
    ) -> dict[str, Any]: ...


async def claim_authorized(session: AsyncSession) -> UUID | None:
    now = datetime.now(UTC)
    row = await session.scalar(
        select(TelephonyCommandJournal)
        .where(
            TelephonyCommandJournal.state.in_(
                (
                    TelephonyCommandState.AUTHORIZED.value,
                    TelephonyCommandState.FAILED_TRANSIENT.value,
                )
            ),
            or_(
                TelephonyCommandJournal.next_attempt_at.is_(None),
                TelephonyCommandJournal.next_attempt_at <= now,
            ),
        )
        .order_by(TelephonyCommandJournal.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if row is None:
        return None
    row.state = TelephonyCommandState.SUBMITTING.value
    row.attempt_count += 1
    row.next_attempt_at = now + timedelta(seconds=60)
    row.updated_at = now
    command_id = row.command_id
    await session.commit()
    return command_id


async def dispatch_one(
    session_factory: async_sessionmaker[AsyncSession],
    client_factory: Callable[[AsyncSession], TelephonyDispatcher],
    *,
    traceparent_factory: Callable[[], str],
) -> dict[str, Any]:
    async with session_factory() as session:
        command_id = await claim_authorized(session)
    if command_id is None:
        return {"claimed": 0}

    async with session_factory() as session:
        row = await session.get(TelephonyCommandJournal, command_id)
        if row is None:
            raise RuntimeError("claimed telephony command disappeared")
        command = TelephonyCommandRequest.model_validate(row.request_json)
        client = client_factory(session)

    try:
        operation = await client.dispatch(
            str(command_id), command, traceparent=traceparent_factory()
        )
        readback = await client.readback(
            command, operation, traceparent=traceparent_factory()
        )
    except Exception:
        async with session_factory() as session:
            row = await session.get(
                TelephonyCommandJournal, command_id, with_for_update=True
            )
            if row is not None and row.state == TelephonyCommandState.SUBMITTING.value:
                row.state = TelephonyCommandState.FAILED_TRANSIENT.value
                row.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(300, 2 ** min(row.attempt_count, 8))
                )
                row.updated_at = datetime.now(UTC)
                await session.commit()
        raise

    state = (
        TelephonyCommandState.SUCCEEDED
        if readback["readback_matches"]
        else TelephonyCommandState.RECONCILIATION_REQUIRED
    )
    async with session_factory() as session:
        row = await session.get(
            TelephonyCommandJournal, command_id, with_for_update=True
        )
        if row is None or row.state != TelephonyCommandState.SUBMITTING.value:
            raise RuntimeError("telephony command finalization state conflict")
        operation_id = UUID(operation["operation_id"])
        existing = await session.get(TelephonyOperationJournal, operation_id)
        if existing is None:
            session.add(
                TelephonyOperationJournal(
                    operation_id=operation_id,
                    command_id=command_id,
                    state=state.value,
                    endpoint_key=operation["endpoint_key"],
                    readback_endpoint_key=operation["readback_endpoint_key"],
                    target_configuration_checksum=operation[
                        "target_configuration_checksum"
                    ],
                    target_attested=operation["target_attested"],
                    desired_hash=operation["desired_hash"],
                    actual_hash=readback["actual_hash"],
                    readback_matches=readback["readback_matches"],
                    correlation_id=command.correlation_id,
                    response_json=readback["actual"],
                    completed_at=datetime.now(UTC),
                )
            )
        row.state = state.value
        row.next_attempt_at = None
        row.updated_at = datetime.now(UTC)
        await session.commit()
    return {
        "claimed": 1,
        "command_id": str(command_id),
        "operation_id": operation["operation_id"],
        "state": state.value,
    }
