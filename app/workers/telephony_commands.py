"""Durable claim/dispatch/readback/finalize telephony command worker."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

import httpx
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.telephony.client import TelephonyClientError
from app.core.telephony_commands import (
    TelephonyCommandRequest,
    TelephonyCommandState,
)
from app.db.models import TelephonyCommandJournal, TelephonyOperationJournal

LEASE_SECONDS = 120
HEARTBEAT_SECONDS = 20
MAX_ATTEMPTS = 8


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


async def claim_authorized(session: AsyncSession) -> tuple[UUID, str] | None:
    now = datetime.now(UTC)
    row = await session.scalar(
        select(TelephonyCommandJournal)
        .where(
            or_(
                and_(
                    TelephonyCommandJournal.state.in_(
                        (
                            TelephonyCommandState.AUTHORIZED.value,
                            TelephonyCommandState.FAILED_TRANSIENT.value,
                            TelephonyCommandState.READBACK_PENDING.value,
                        )
                    ),
                    or_(
                        TelephonyCommandJournal.next_attempt_at.is_(None),
                        TelephonyCommandJournal.next_attempt_at <= now,
                    ),
                ),
                and_(
                    TelephonyCommandJournal.state
                    == TelephonyCommandState.SUBMITTING.value,
                    TelephonyCommandJournal.next_attempt_at <= now,
                ),
            ),
        )
        .order_by(TelephonyCommandJournal.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if row is None:
        return None
    owner = uuid4().hex
    row.state = TelephonyCommandState.SUBMITTING.value
    row.attempt_count += 1
    row.lease_owner = owner
    row.next_attempt_at = now + timedelta(seconds=LEASE_SECONDS)
    row.updated_at = now
    command_id = row.command_id
    await session.commit()
    return command_id, owner


async def _renew_lease(
    session_factory: async_sessionmaker[AsyncSession],
    command_id: UUID,
    owner: str,
) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        async with session_factory() as session:
            row = await session.get(
                TelephonyCommandJournal, command_id, with_for_update=True
            )
            if (
                row is None
                or row.state != TelephonyCommandState.SUBMITTING.value
                or row.lease_owner != owner
            ):
                return
            row.next_attempt_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
            row.updated_at = datetime.now(UTC)
            await session.commit()


async def _claim_readback(
    session_factory: async_sessionmaker[AsyncSession], command_id: UUID
) -> str:
    async with session_factory() as session:
        row = await session.get(
            TelephonyCommandJournal, command_id, with_for_update=True
        )
        if (
            row is None
            or row.state != TelephonyCommandState.READBACK_PENDING.value
        ):
            raise RuntimeError("telephony readback claim conflict")
        owner = uuid4().hex
        row.state = TelephonyCommandState.SUBMITTING.value
        row.lease_owner = owner
        row.next_attempt_at = datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)
        row.updated_at = datetime.now(UTC)
        await session.commit()
        return owner


def _permanent(exc: Exception) -> bool:
    if isinstance(exc, TelephonyClientError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return 400 <= status < 500 and status not in {408, 409, 425, 429}
    return False


async def _record_failure(
    session_factory: async_sessionmaker[AsyncSession],
    command_id: UUID,
    owner: str,
    exc: Exception,
) -> None:
    async with session_factory() as session:
        row = await session.get(
            TelephonyCommandJournal, command_id, with_for_update=True
        )
        if (
            row is None
            or row.state != TelephonyCommandState.SUBMITTING.value
            or row.lease_owner != owner
        ):
            return
        permanent = _permanent(exc) or row.attempt_count >= MAX_ATTEMPTS
        row.state = (
            TelephonyCommandState.FAILED_PERMANENT.value
            if permanent
            else TelephonyCommandState.FAILED_TRANSIENT.value
        )
        row.next_attempt_at = (
            None
            if permanent
            else datetime.now(UTC)
            + timedelta(seconds=min(300, 2 ** min(row.attempt_count, 8)))
        )
        row.lease_owner = None
        row.updated_at = datetime.now(UTC)
        await session.commit()


async def _persist_submission(
    session_factory: async_sessionmaker[AsyncSession],
    command_id: UUID,
    owner: str,
    command: TelephonyCommandRequest,
    operation: dict[str, Any],
) -> None:
    async with session_factory() as session:
        row = await session.get(
            TelephonyCommandJournal, command_id, with_for_update=True
        )
        if (
            row is None
            or row.state != TelephonyCommandState.SUBMITTING.value
            or row.lease_owner != owner
        ):
            raise RuntimeError("telephony command submission ownership conflict")
        operation_id = UUID(operation["operation_id"])
        existing_for_command = await session.scalar(
            select(TelephonyOperationJournal).where(
                TelephonyOperationJournal.command_id == command_id
            )
        )
        if existing_for_command is None:
            session.add(
                TelephonyOperationJournal(
                    operation_id=operation_id,
                    command_id=command_id,
                    state=TelephonyCommandState.SUBMITTED.value,
                    endpoint_key=operation["endpoint_key"],
                    readback_endpoint_key=operation["readback_endpoint_key"],
                    target_configuration_checksum=operation[
                        "target_configuration_checksum"
                    ],
                    target_attested=operation["target_attested"],
                    desired_hash=operation["desired_hash"],
                    correlation_id=command.correlation_id,
                    response_json={},
                )
            )
        elif existing_for_command.operation_id != operation_id:
            raise RuntimeError("adapter operation idempotency conflict")
        row.state = TelephonyCommandState.READBACK_PENDING.value
        row.next_attempt_at = datetime.now(UTC)
        row.lease_owner = None
        row.updated_at = datetime.now(UTC)
        await session.commit()


async def dispatch_one(
    session_factory: async_sessionmaker[AsyncSession],
    client_factory: Callable[[], TelephonyDispatcher],
    *,
    traceparent_factory: Callable[[], str],
) -> dict[str, Any]:
    async with session_factory() as session:
        claim = await claim_authorized(session)
    if claim is None:
        return {"claimed": 0}
    command_id, owner = claim

    async with session_factory() as session:
        row = await session.get(TelephonyCommandJournal, command_id)
        if row is None:
            raise RuntimeError("claimed telephony command disappeared")
        command = TelephonyCommandRequest.model_validate(row.request_json)
        existing = await session.scalar(
            select(TelephonyOperationJournal).where(
                TelephonyOperationJournal.command_id == command_id
            )
        )
        operation = (
            {
                "operation_id": str(existing.operation_id),
                "endpoint_key": existing.endpoint_key,
                "readback_endpoint_key": existing.readback_endpoint_key,
                "target_configuration_checksum": (
                    existing.target_configuration_checksum
                ),
                "target_attested": existing.target_attested,
                "desired_hash": existing.desired_hash,
            }
            if existing
            else None
        )

    client = client_factory()
    heartbeat = asyncio.create_task(_renew_lease(session_factory, command_id, owner))
    try:
        if operation is None:
            operation = await client.dispatch(
                str(command_id), command, traceparent=traceparent_factory()
            )
            await _persist_submission(
                session_factory, command_id, owner, command, operation
            )
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat
            # The submission transaction deliberately releases ownership before
            # readback. Reclaim it immediately using the durable operation row.
            owner = await _claim_readback(session_factory, command_id)
            heartbeat = asyncio.create_task(
                _renew_lease(session_factory, command_id, owner)
            )
        readback = await client.readback(
            command, operation, traceparent=traceparent_factory()
        )
    except Exception as exc:
        await _record_failure(session_factory, command_id, owner, exc)
        raise
    finally:
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat

    state = (
        TelephonyCommandState.SUCCEEDED
        if readback["readback_matches"]
        else TelephonyCommandState.RECONCILIATION_REQUIRED
    )
    async with session_factory() as session:
        row = await session.get(
            TelephonyCommandJournal, command_id, with_for_update=True
        )
        operation_row = await session.scalar(
            select(TelephonyOperationJournal).where(
                TelephonyOperationJournal.command_id == command_id
            )
        )
        if (
            row is None
            or operation_row is None
            or row.state != TelephonyCommandState.SUBMITTING.value
            or row.lease_owner != owner
        ):
            raise RuntimeError("telephony command finalization state conflict")
        operation_row.state = state.value
        operation_row.actual_hash = readback["actual_hash"]
        operation_row.readback_matches = readback["readback_matches"]
        operation_row.response_json = readback["actual"]
        operation_row.completed_at = datetime.now(UTC)
        row.state = state.value
        row.next_attempt_at = None
        row.lease_owner = None
        row.updated_at = datetime.now(UTC)
        await session.commit()
    return {
        "claimed": 1,
        "command_id": str(command_id),
        "operation_id": operation["operation_id"],
        "state": state.value,
    }
