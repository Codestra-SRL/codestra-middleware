"""Durable telephony command and operation journals.

POST creates a command only.  Dispatch remains an asynchronous, policy-gated
worker concern; the API never writes directly to telephony systems.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telephony_commands import (
    MUTATION_ENDPOINTS,
    READBACK_ENDPOINTS,
    TelephonyCommandRequest,
    new_command_record,
    payload_hash,
)
from app.db.models import (
    PolicyDecision,
    TelephonyCommandJournal,
    TelephonyOperationJournal,
    TelephonyOperationTransition,
    TelephonyReconciliationRun,
    TelephonyTerminalResult,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["commands"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
IdempotencyHeader = Annotated[str, Header(alias="Idempotency-Key")]
AdapterIdentityHeader = Annotated[str, Header(alias="X-Codestra-Client-ID")]


def _command_targets(command: TelephonyCommandRequest) -> set[str]:
    payload = command.payload
    return {
        value
        for value in (
            payload.endpoint_public_id,
            payload.source_endpoint_public_id,
            payload.destination_endpoint_public_id,
            payload.agent_public_id,
            payload.phone_public_id,
            payload.call_public_id,
        )
        if value
    }


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
@router.post("/telephony/commands", status_code=202)
async def create_command(
    body: TelephonyCommandRequest,
    idempotency_key: IdempotencyHeader,
    session: SessionDep,
):
    if idempotency_key != body.idempotency_key:
        raise HTTPException(400, "header and command idempotency keys must match")
    decision = (
        await session.get(PolicyDecision, UUID(body.policy_decision_id))
        if body.policy_decision_id
        else await session.scalar(
            select(PolicyDecision)
            .where(PolicyDecision.correlation_id == body.correlation_id)
            .order_by(PolicyDecision.created_at.desc())
            .limit(1)
        )
    )
    if not decision:
        raise HTTPException(422, "policy decision not found")
    if body.policy_decision_id is None:
        body = body.model_copy(update={"policy_decision_id": str(decision.id)})
    values = new_command_record(body)
    existing = await session.scalar(
        select(TelephonyCommandJournal).where(
            TelephonyCommandJournal.idempotency_hash == values["idempotency_hash"]
        )
    )
    if existing:
        if existing.request_hash != values["request_hash"]:
            raise HTTPException(409, "idempotency key conflict")
        return _command_view(existing, replayed=True)
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
    aggregate_lock_key = (
        f"{body.environment}\x1f{body.aggregate_type}\x1f{body.aggregate_public_id}"
    )
    await session.execute(
        select(func.pg_advisory_xact_lock(func.hashtextextended(aggregate_lock_key, 0)))
    )
    latest_version = await session.scalar(
        select(func.max(TelephonyCommandJournal.aggregate_version)).where(
            TelephonyCommandJournal.environment == body.environment,
            TelephonyCommandJournal.aggregate_type == body.aggregate_type,
            TelephonyCommandJournal.aggregate_public_id == body.aggregate_public_id,
        )
    )
    if latest_version is not None and body.aggregate_version <= latest_version:
        raise HTTPException(409, "stale or duplicate aggregate version")
    values["state"] = (
        "AUTHORIZED"
        if decision.allowed and decision.context.get("enforced") is True
        else "POLICY_DENIED"
    )
    row = TelephonyCommandJournal(**values)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(TelephonyCommandJournal).where(
                TelephonyCommandJournal.idempotency_hash == values["idempotency_hash"]
            )
        )
        if not existing or existing.request_hash != values["request_hash"]:
            latest_version = await session.scalar(
                select(func.max(TelephonyCommandJournal.aggregate_version)).where(
                    TelephonyCommandJournal.environment == body.environment,
                    TelephonyCommandJournal.aggregate_type == body.aggregate_type,
                    TelephonyCommandJournal.aggregate_public_id
                    == body.aggregate_public_id,
                )
            )
            if latest_version is not None and body.aggregate_version <= latest_version:
                raise HTTPException(
                    409, "stale or duplicate aggregate version"
                ) from None
            raise HTTPException(409, "concurrent command conflict") from None
        return _command_view(existing, replayed=True)
    return _command_view(row)


@router.get("/commands/{command_public_id}")
@router.get("/telephony/commands/{command_public_id}")
async def get_command(
    command_public_id: UUID, session: SessionDep
):
    row = await session.get(TelephonyCommandJournal, command_public_id)
    if not row:
        raise HTTPException(404, "command not found")
    return _command_view(row)


@router.post("/telephony/commands/{command_public_id}/cancel")
async def cancel_command(
    command_public_id: UUID, session: SessionDep
):
    row = await session.get(
        TelephonyCommandJournal, command_public_id, with_for_update=True
    )
    if not row:
        raise HTTPException(404, "command not found")
    if row.state in {"SUCCEEDED", "RECONCILED", "FAILED_PERMANENT"}:
        raise HTTPException(409, "terminal command cannot be cancelled")
    row.state = "CANCELLED"
    row.lease_owner = None
    row.next_attempt_at = None
    row.updated_at = datetime.now(UTC)
    await session.commit()
    return _command_view(row)


class OperationRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_public_id: UUID
    command_public_id: UUID
    adapter_identity: str = Field(min_length=4, max_length=144)
    target_public_id: str = Field(min_length=4, max_length=144)
    environment: Literal["staging", "test", "production"]
    desired_state_version: int = Field(ge=1)
    endpoint_key: str = Field(min_length=1, max_length=96)
    readback_endpoint_key: str = Field(min_length=1, max_length=96)
    target_configuration_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    desired_state_hash: str = Field(pattern=r"^(?:sha256:)?[0-9a-f]{64}$")
    target_attested: Literal[True]
    correlation_id: str = Field(min_length=1, max_length=128)


@router.post("/telephony/operations", status_code=202)
async def register_operation(
    body: OperationRegistration,
    adapter_identity_header: AdapterIdentityHeader,
    session: SessionDep,
):
    command = await session.get(
        TelephonyCommandJournal, body.command_public_id, with_for_update=True
    )
    if not command:
        raise HTTPException(404, "command not found")
    if (
        command.correlation_id != body.correlation_id
        or adapter_identity_header != body.adapter_identity
    ):
        raise HTTPException(409, "operation correlation binding mismatch")
    request = TelephonyCommandRequest.model_validate(command.request_json)
    if (
        command.environment != body.environment
        or request.payload.desired_state_version != body.desired_state_version
        or body.target_public_id not in _command_targets(request)
        or MUTATION_ENDPOINTS[request.command_type] != body.endpoint_key
        or READBACK_ENDPOINTS[request.command_type] != body.readback_endpoint_key
    ):
        raise HTTPException(409, "operation target or desired-state binding mismatch")
    prior = await session.scalar(
        select(TelephonyOperationJournal).where(
            TelephonyOperationJournal.command_id == body.command_public_id
        )
    )
    immutable = {
        "operation_id": body.operation_public_id,
        "adapter_identity": body.adapter_identity,
        "target_public_id": body.target_public_id,
        "environment": body.environment,
        "desired_state_version": body.desired_state_version,
        "endpoint_key": body.endpoint_key,
        "readback_endpoint_key": body.readback_endpoint_key,
        "target_configuration_checksum": body.target_configuration_checksum,
        "desired_hash": body.desired_state_hash.removeprefix("sha256:"),
        "correlation_id": body.correlation_id,
    }
    if prior:
        if any(getattr(prior, key) != value for key, value in immutable.items()):
            raise HTTPException(409, "immutable operation binding conflict")
        return {
            "operation_public_id": str(prior.operation_id),
            "idempotency_status": "DUPLICATE",
        }
    row = TelephonyOperationJournal(
        **immutable,
        command_id=body.command_public_id,
        state="OPERATION_REGISTERED",
        target_attested=True,
        response_json={},
    )
    session.add(row)
    command.state = "OPERATION_REGISTERED"
    command.updated_at = datetime.now(UTC)
    await session.commit()
    return {"operation_public_id": str(row.operation_id), "idempotency_status": "NEW"}


@router.get("/telephony/operations/{operation_public_id}")
async def get_operation(
    operation_public_id: UUID, session: SessionDep
):
    row = await session.get(TelephonyOperationJournal, operation_public_id)
    if not row:
        raise HTTPException(404, "operation not found")
    return {
        "operation_id": str(row.operation_id),
        "command_id": str(row.command_id),
        "state": row.state,
        "adapter_identity": row.adapter_identity,
        "target_public_id": row.target_public_id,
        "environment": row.environment,
        "desired_state_version": row.desired_state_version,
        "endpoint_key": row.endpoint_key,
        "readback_endpoint_key": row.readback_endpoint_key,
        "target_attested": row.target_attested,
        "desired_hash": row.desired_hash,
        "actual_hash": row.actual_hash,
        "readback_matches": row.readback_matches,
        "correlation_id": row.correlation_id,
        "completed_at": row.completed_at,
    }


class OperationTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal[
        "APPLYING",
        "APPLIED",
        "READBACK_PENDING",
        "READBACK_VERIFIED",
        "ODOO_RESULT_PENDING",
        "ODOO_RESULT_DELIVERED",
        "RECONCILED",
        "RECONCILIATION_REQUIRED",
        "FAILED_PERMANENT",
    ]
    correlation_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=1)
    transition_hash: str = Field(pattern=r"^(?:sha256:)?[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=8, max_length=255)
    adapter_identity: str = Field(min_length=4, max_length=144)
    evidence: dict = Field(default_factory=dict)


_TRANSITIONS = {
    "OPERATION_REGISTERED": {"APPLYING"},
    "APPLYING": {"APPLIED", "FAILED_PERMANENT", "RECONCILIATION_REQUIRED"},
    "APPLIED": {"READBACK_PENDING"},
    "READBACK_PENDING": {"READBACK_VERIFIED", "RECONCILIATION_REQUIRED"},
    "READBACK_VERIFIED": {"ODOO_RESULT_PENDING"},
    "ODOO_RESULT_PENDING": {"ODOO_RESULT_DELIVERED", "RECONCILIATION_REQUIRED"},
    "ODOO_RESULT_DELIVERED": {"RECONCILED", "RECONCILIATION_REQUIRED"},
}


@router.post("/telephony/operations/{operation_public_id}/transitions")
async def transition_operation(
    operation_public_id: UUID,
    body: OperationTransition,
    adapter_identity_header: AdapterIdentityHeader,
    session: SessionDep,
):
    row = await session.get(
        TelephonyOperationJournal, operation_public_id, with_for_update=True
    )
    if not row:
        raise HTTPException(404, "operation not found")
    if row.correlation_id != body.correlation_id:
        raise HTTPException(409, "operation correlation binding mismatch")
    if (
        row.adapter_identity != body.adapter_identity
        or adapter_identity_header != body.adapter_identity
    ):
        raise HTTPException(409, "operation adapter identity mismatch")
    prior = await session.scalar(
        select(TelephonyOperationTransition).where(
            TelephonyOperationTransition.operation_id == operation_public_id,
            TelephonyOperationTransition.idempotency_key == body.idempotency_key,
        )
    )
    immutable_hash = body.transition_hash.removeprefix("sha256:")
    if prior:
        if (
            prior.sequence != body.sequence
            or prior.to_state != body.state
            or prior.transition_hash != immutable_hash
        ):
            raise HTTPException(409, "transition idempotency conflict")
        return {
            "operation_public_id": str(row.operation_id),
            "state": prior.to_state,
            "sequence": prior.sequence,
            "idempotency_status": "DUPLICATE",
        }
    expected_sequence = (
        await session.scalar(
            select(func.max(TelephonyOperationTransition.sequence)).where(
                TelephonyOperationTransition.operation_id == operation_public_id
            )
        )
        or 0
    ) + 1
    if body.sequence != expected_sequence:
        raise HTTPException(409, "out-of-order operation transition")
    expected_hash = payload_hash(
        {
            "operation_public_id": str(operation_public_id),
            "sequence": body.sequence,
            "from_state": row.state,
            "to_state": body.state,
            "adapter_identity": body.adapter_identity,
            "correlation_id": body.correlation_id,
            "evidence": body.evidence,
        }
    )
    if immutable_hash != expected_hash:
        raise HTTPException(409, "operation transition hash mismatch")
    if body.state == row.state:
        return {
            "operation_public_id": str(row.operation_id),
            "state": row.state,
            "idempotency_status": "DUPLICATE",
        }
    if body.state not in _TRANSITIONS.get(row.state, set()):
        raise HTTPException(409, "invalid operation transition")
    from_state = row.state
    row.state = body.state
    session.add(
        TelephonyOperationTransition(
            operation_id=operation_public_id,
            sequence=body.sequence,
            from_state=from_state,
            to_state=body.state,
            transition_hash=immutable_hash,
            idempotency_key=body.idempotency_key,
            adapter_identity=body.adapter_identity,
            correlation_id=body.correlation_id,
            evidence_json=body.evidence,
        )
    )
    if body.state in {"RECONCILED", "FAILED_PERMANENT"}:
        row.completed_at = datetime.now(UTC)
    await session.commit()
    return {
        "operation_public_id": str(row.operation_id),
        "state": row.state,
        "sequence": body.sequence,
        "idempotency_status": "NEW",
    }


class TerminalResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_public_id: UUID
    operation_public_id: UUID
    command_public_id: UUID
    adapter_identity: str = Field(min_length=4, max_length=144)
    target_public_id: str = Field(min_length=4, max_length=144)
    environment: Literal["staging", "test", "production"]
    requested_state_version: int = Field(ge=1)
    applied_state_version: int = Field(ge=1)
    observed_state_version: int = Field(ge=1)
    result_hash: str = Field(pattern=r"^(?:sha256:)?[0-9a-f]{64}$")
    application_hash: str = Field(pattern=r"^(?:sha256:)?[0-9a-f]{64}$")
    readback_hash: str = Field(pattern=r"^(?:sha256:)?[0-9a-f]{64}$")
    policy_hash: str = Field(pattern=r"^(?:sha256:)?[0-9a-f]{64}$")
    status: Literal["APPLIED", "FAILED", "STALE"]
    reconciliation_status: Literal["IN_SYNC", "RECONCILIATION_REQUIRED"]
    correlation_id: str = Field(min_length=1, max_length=128)


def _result_view(row: TelephonyTerminalResult, duplicate: bool = False) -> dict:
    return {
        "result_public_id": str(row.result_id),
        "operation_public_id": str(row.operation_id),
        "command_public_id": str(row.command_id),
        "status": row.status,
        "reconciliation_status": row.reconciliation_status,
        "correlation_id": row.correlation_id,
        "idempotency_status": "DUPLICATE" if duplicate else "NEW",
    }


@router.post("/telephony/results", status_code=202)
async def create_terminal_result(
    body: TerminalResultRequest,
    adapter_identity_header: AdapterIdentityHeader,
    session: SessionDep,
):
    immutable = body.model_dump(mode="json")
    expected_result_hash = payload_hash(
        {
            key: value
            for key, value in immutable.items()
            if key != "result_hash"
        }
    )
    if body.result_hash.removeprefix("sha256:") != expected_result_hash:
        raise HTTPException(409, "terminal result hash mismatch")
    prior = await session.scalar(
        select(TelephonyTerminalResult).where(
            (TelephonyTerminalResult.result_id == body.result_public_id)
            | (TelephonyTerminalResult.operation_id == body.operation_public_id)
        )
    )
    if prior:
        if prior.immutable_json != immutable:
            raise HTTPException(409, "IMMUTABLE_RESULT_BINDING_CONFLICT")
        return _result_view(prior, duplicate=True)
    operation = await session.get(
        TelephonyOperationJournal, body.operation_public_id, with_for_update=True
    )
    command = await session.get(TelephonyCommandJournal, body.command_public_id)
    if (
        not operation
        or not command
        or operation.command_id != command.command_id
        or command.correlation_id != body.correlation_id
        or command.policy_decision_hash != body.policy_hash.removeprefix("sha256:")
        or operation.adapter_identity != body.adapter_identity
        or operation.target_public_id != body.target_public_id
        or operation.environment != body.environment
        or command.environment != body.environment
        or operation.desired_state_version != body.requested_state_version
        or body.applied_state_version != body.requested_state_version
        or body.observed_state_version != body.requested_state_version
        or adapter_identity_header != body.adapter_identity
    ):
        raise HTTPException(409, "terminal result binding mismatch")
    row = TelephonyTerminalResult(
        result_id=body.result_public_id,
        operation_id=body.operation_public_id,
        command_id=body.command_public_id,
        adapter_identity=body.adapter_identity,
        target_public_id=body.target_public_id,
        environment=body.environment,
        requested_state_version=body.requested_state_version,
        applied_state_version=body.applied_state_version,
        observed_state_version=body.observed_state_version,
        result_hash=body.result_hash.removeprefix("sha256:"),
        application_hash=body.application_hash.removeprefix("sha256:"),
        readback_hash=body.readback_hash.removeprefix("sha256:"),
        policy_hash=body.policy_hash.removeprefix("sha256:"),
        status=body.status,
        reconciliation_status=body.reconciliation_status,
        correlation_id=body.correlation_id,
        immutable_json=immutable,
    )
    session.add(row)
    operation.state = (
        "READBACK_VERIFIED"
        if body.reconciliation_status == "IN_SYNC"
        else "RECONCILIATION_REQUIRED"
    )
    await session.commit()
    return _result_view(row)


@router.get("/telephony/results/{result_public_id}")
async def get_terminal_result(
    result_public_id: UUID, session: SessionDep
):
    row = await session.get(TelephonyTerminalResult, result_public_id)
    if not row:
        raise HTTPException(404, "result not found")
    return _result_view(row)


class ReconciliationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_public_id: UUID = Field(default_factory=uuid4)
    command_public_id: UUID | None = None
    environment: Literal["staging", "test", "production"]
    aggregate_type: str = Field(min_length=1, max_length=64)
    aggregate_public_id: str = Field(min_length=1, max_length=144)
    target_system: Literal["VICIDIAL", "ASTERISK"]
    classification: str = Field(min_length=1, max_length=64)
    correlation_id: str = Field(min_length=1, max_length=128)
    evidence: dict = Field(default_factory=dict)


@router.post("/telephony/reconciliation/runs", status_code=202)
async def create_reconciliation_run(
    body: ReconciliationRunRequest, session: SessionDep
):
    prior = await session.get(TelephonyReconciliationRun, body.run_public_id)
    if prior:
        return {
            "run_public_id": str(prior.run_id),
            "status": prior.status,
            "idempotency_status": "DUPLICATE",
        }
    row = TelephonyReconciliationRun(
        run_id=body.run_public_id,
        command_id=body.command_public_id,
        environment=body.environment,
        aggregate_type=body.aggregate_type,
        aggregate_public_id=body.aggregate_public_id,
        target_system=body.target_system,
        status="REQUESTED",
        classification=body.classification,
        correlation_id=body.correlation_id,
        evidence_json=body.evidence,
    )
    session.add(row)
    await session.commit()
    return {
        "run_public_id": str(row.run_id),
        "status": row.status,
        "idempotency_status": "NEW",
    }


@router.get("/telephony/reconciliation/runs/{run_public_id}")
async def get_reconciliation_run(
    run_public_id: UUID, session: SessionDep
):
    row = await session.get(TelephonyReconciliationRun, run_public_id)
    if not row:
        raise HTTPException(404, "reconciliation run not found")
    return {
        "run_public_id": str(row.run_id),
        "status": row.status,
        "classification": row.classification,
        "correlation_id": row.correlation_id,
    }
