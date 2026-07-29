"""Durable telephony command and operation journals.

POST creates a command only.  Dispatch remains an asynchronous, policy-gated
worker concern; the API never writes directly to telephony systems.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telephony_commands import TelephonyCommandRequest, new_command_record
from app.core.telephony_commands import payload_hash
from app.db.models import (
    PolicyDecision,
    TelephonyCommandJournal,
    TelephonyOperationJournal,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["commands"])


def _command_view(row: TelephonyCommandJournal, *, replayed: bool = False) -> dict:
    return {
        "command_id": str(row.command_id),
        "command_type": row.command_type,
        "aggregate_public_id": row.aggregate_public_id,
        "aggregate_version": row.aggregate_version,
        "state": row.state,
        "correlation_id": row.correlation_id,
        "replayed": replayed,
    }


@router.post("/commands", status_code=202)
async def create_command(
    body: TelephonyCommandRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
):
    if idempotency_key != body.idempotency_key:
        raise HTTPException(400, "header and command idempotency keys must match")
    values = new_command_record(body)
    decision = await session.get(PolicyDecision, UUID(body.policy_decision_id))
    if not decision:
        raise HTTPException(422, "policy decision not found")
    if decision.correlation_id != body.correlation_id:
        raise HTTPException(409, "policy correlation mismatch")
    if payload_hash(decision.context) != body.policy_decision_hash:
        raise HTTPException(409, "policy decision hash mismatch")
    if decision.context.get("authorization_scope") != body.policy_scope():
        raise HTTPException(409, "policy authorization scope mismatch")
    expiration = decision.context.get("expiration")
    if not isinstance(expiration, str):
        raise HTTPException(409, "policy expiration is invalid")
    try:
        expires_at = datetime.fromisoformat(expiration)
    except (TypeError, ValueError):
        raise HTTPException(409, "policy expiration is invalid") from None
    if expires_at.tzinfo is None or expires_at <= datetime.now(UTC):
        raise HTTPException(409, "policy decision expired")
    values["state"] = (
        "AUTHORIZED"
        if decision.allowed and decision.context.get("enforced") is True
        else "POLICY_DENIED"
    )
    existing = await session.scalar(
        select(TelephonyCommandJournal).where(
            TelephonyCommandJournal.idempotency_hash == values["idempotency_hash"]
        )
    )
    if existing:
        if existing.request_hash != values["request_hash"]:
            raise HTTPException(409, "idempotency key conflict")
        return _command_view(existing, replayed=True)
    row = TelephonyCommandJournal(**values)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(TelephonyCommandJournal).where(
                TelephonyCommandJournal.idempotency_hash
                == values["idempotency_hash"]
            )
        )
        if not existing or existing.request_hash != values["request_hash"]:
            raise HTTPException(409, "concurrent idempotency conflict") from None
        return _command_view(existing, replayed=True)
    return _command_view(row)


@router.get("/commands/{command_id}")
async def get_command(
    command_id: UUID, session: AsyncSession = Depends(get_session)
):
    row = await session.get(TelephonyCommandJournal, command_id)
    if not row:
        raise HTTPException(404, "command not found")
    return _command_view(row)


@router.get("/telephony/operations/{operation_id}")
async def get_operation(
    operation_id: UUID, session: AsyncSession = Depends(get_session)
):
    row = await session.get(TelephonyOperationJournal, operation_id)
    if not row:
        raise HTTPException(404, "operation not found")
    return {
        "operation_id": str(row.operation_id),
        "command_id": str(row.command_id),
        "state": row.state,
        "endpoint_key": row.endpoint_key,
        "readback_endpoint_key": row.readback_endpoint_key,
        "target_attested": row.target_attested,
        "desired_hash": row.desired_hash,
        "actual_hash": row.actual_hash,
        "readback_matches": row.readback_matches,
        "correlation_id": row.correlation_id,
        "completed_at": row.completed_at,
    }
