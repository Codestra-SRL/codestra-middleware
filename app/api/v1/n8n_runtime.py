"""Canonical tenant-bound n8n dispatch and authenticated result callback."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.n8n_runtime import (
    DispatchRequest,
    ExecutionStatus,
    ResultContract,
    canonical_bytes,
    load_secret,
    sha256,
    verify_fresh,
    verify_runtime,
)
from app.db.models import (
    AuditEvent,
    N8nRuntimeExecution,
    N8nRuntimeNonce,
    N8nRuntimeResult,
    N8nWorkflowRegistry,
)
from app.db.session import get_session
from app.metrics import N8N_DISPATCH, N8N_RESULT, N8N_RESULT_FAILURE

router = APIRouter(prefix="/api/v1/n8n-runtime", tags=["n8n-runtime"])


def _safe_execution(
    value: N8nRuntimeExecution, duplicate: bool = False
) -> dict[str, Any]:
    return {
        "schema_version": "codestra.n8n.execution.v1",
        "execution_id": str(value.execution_id),
        "tenant_id": value.tenant_id,
        "event_id": value.event_id,
        "workflow_code": value.workflow_code,
        "workflow_version": value.workflow_version,
        "status": value.status,
        "correlation_id": value.correlation_id,
        "duplicate": duplicate,
    }


@router.post("/dispatch", status_code=status.HTTP_202_ACCEPTED)
async def dispatch(
    body: DispatchRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    if not settings.n8n_runtime_enabled:
        raise HTTPException(503, "governed n8n runtime is disabled")
    payload_hash = sha256(canonical_bytes(body.payload))
    key_hash = hashlib.sha256(body.idempotency_key.encode()).hexdigest()
    lock_scope = f"{body.tenant_id}:{body.event_type}:{body.source_event_id}:{key_hash}"
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": lock_scope},
    )
    registry = await db.scalar(
        select(N8nWorkflowRegistry).where(
            N8nWorkflowRegistry.enabled.is_(True),
            N8nWorkflowRegistry.event_types.contains([body.event_type]),
            N8nWorkflowRegistry.tenant_scope.contains([body.tenant_id]),
        )
    )
    if registry is None:
        await db.rollback()
        raise HTTPException(403, "no approved workflow mapping")
    existing = await db.scalar(
        select(N8nRuntimeExecution).where(
            N8nRuntimeExecution.tenant_id == body.tenant_id,
            N8nRuntimeExecution.event_type == body.event_type,
            N8nRuntimeExecution.source_event_id == body.source_event_id,
            N8nRuntimeExecution.workflow_version == registry.workflow_version,
            N8nRuntimeExecution.idempotency_key_hash == key_hash,
        )
    )
    if existing is not None:
        if existing.payload_hash != payload_hash:
            await db.rollback()
            raise HTTPException(409, "workflow payload conflict")
        await db.commit()
        response.status_code = status.HTTP_200_OK
        N8N_DISPATCH.labels(outcome="duplicate").inc()
        return _safe_execution(existing, True)
    now = datetime.now(UTC)
    execution = N8nRuntimeExecution(
        execution_id=uuid4(),
        tenant_id=body.tenant_id,
        event_id=body.event_id,
        event_type=body.event_type,
        source_event_id=body.source_event_id,
        workflow_code=registry.workflow_code,
        workflow_version=registry.workflow_version,
        correlation_id=body.correlation_id,
        causation_id=body.causation_id,
        trace_id=body.trace_id,
        idempotency_key_hash=key_hash,
        payload_hash=payload_hash,
        payload_json=body.payload,
        status=ExecutionStatus.PENDING,
        timeout_at=now + timedelta(seconds=registry.timeout_seconds),
    )
    db.add(execution)
    db.add(
        AuditEvent(
            action="n8n.runtime.created",
            subject=str(execution.execution_id),
            correlation_id=body.correlation_id,
            decision="accepted",
            redacted_payload={
                "tenant_id": body.tenant_id,
                "event_id": body.event_id,
                "workflow_code": registry.workflow_code,
                "workflow_version": registry.workflow_version,
                "payload_hash": payload_hash,
            },
        )
    )
    await db.commit()
    N8N_DISPATCH.labels(outcome="created").inc()
    return _safe_execution(execution)


@router.get("/executions/{execution_id}")
async def execution_status(
    execution_id: UUID,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    execution = await db.get(N8nRuntimeExecution, execution_id)
    if execution is None or execution.tenant_id != tenant_id:
        raise HTTPException(404, "execution not found")
    return _safe_execution(execution)


@router.post("/results", status_code=202)
async def result_callback(
    request: Request,
    response: Response,
    x_codestra_identity: Annotated[str, Header(alias="X-Codestra-Identity")],
    x_codestra_tenant: Annotated[str, Header(alias="X-Codestra-Tenant")],
    x_codestra_workflow: Annotated[str, Header(alias="X-Codestra-Workflow")],
    x_codestra_execution: Annotated[str, Header(alias="X-Codestra-Execution")],
    x_codestra_correlation_id: Annotated[
        str, Header(alias="X-Codestra-Correlation-ID")
    ],
    x_codestra_timestamp: Annotated[str, Header(alias="X-Codestra-Timestamp")],
    x_codestra_nonce: Annotated[str, Header(alias="X-Codestra-Nonce")],
    x_codestra_body_sha256: Annotated[str, Header(alias="X-Codestra-Body-SHA256")],
    x_codestra_signature: Annotated[str, Header(alias="X-Codestra-Signature")],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    raw = await request.body()
    body_hash = sha256(raw)
    try:
        verify_fresh(x_codestra_timestamp, settings.signature_ttl_seconds)
        if body_hash != x_codestra_body_sha256.removeprefix("sha256:"):
            raise ValueError("body hash mismatch")
        verify_runtime(
            x_codestra_signature,
            load_secret(settings.n8n_runtime_hmac_secret_file),
            identity=x_codestra_identity,
            tenant_id=x_codestra_tenant,
            workflow_code=x_codestra_workflow,
            execution_id=x_codestra_execution,
            correlation_id=x_codestra_correlation_id,
            timestamp=x_codestra_timestamp,
            nonce=x_codestra_nonce,
            body_hash=body_hash,
        )
        body = ResultContract.model_validate_json(raw)
        execution_id = UUID(x_codestra_execution)
    except (RuntimeError, ValueError) as exc:
        N8N_RESULT_FAILURE.labels(reason="authentication_or_contract").inc()
        raise HTTPException(
            401, "invalid n8n result authentication or contract"
        ) from exc
    execution = await db.get(N8nRuntimeExecution, execution_id, with_for_update=True)
    if (
        execution is None
        or execution.tenant_id != x_codestra_tenant
        or execution.workflow_code != x_codestra_workflow
        or execution.correlation_id != x_codestra_correlation_id
        or body.tenant_id != execution.tenant_id
        or body.workflow_code != execution.workflow_code
        or body.workflow_version != execution.workflow_version
        or body.execution_id != str(execution.execution_id)
        or body.correlation_id != execution.correlation_id
    ):
        await db.rollback()
        N8N_RESULT_FAILURE.labels(reason="binding").inc()
        raise HTTPException(409, "n8n result binding mismatch")
    if await db.get(N8nRuntimeNonce, (x_codestra_identity, x_codestra_nonce)):
        await db.rollback()
        N8N_RESULT_FAILURE.labels(reason="replay").inc()
        raise HTTPException(409, "replayed n8n result")
    db.add(
        N8nRuntimeNonce(
            identity=x_codestra_identity,
            nonce=x_codestra_nonce,
            tenant_id=execution.tenant_id,
            execution_id=execution.execution_id,
            body_hash=body_hash,
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.signature_ttl_seconds),
        )
    )
    result_hash = sha256(canonical_bytes(body))
    prior = await db.scalar(
        select(N8nRuntimeResult).where(
            N8nRuntimeResult.execution_id == execution.execution_id,
            N8nRuntimeResult.result_hash == result_hash,
        )
    )
    if prior is not None:
        await db.commit()
        response.status_code = 200
        return {
            "accepted": True,
            "duplicate": True,
            "execution_id": str(execution.execution_id),
        }
    mapped = {
        "running": ExecutionStatus.RUNNING,
        "completed": ExecutionStatus.COMPLETED,
        "failed": ExecutionStatus.FAILED,
        "retry": ExecutionStatus.RETRY,
        "dead_letter": ExecutionStatus.DEAD_LETTER,
    }[body.status]
    execution.status = mapped
    execution.n8n_execution_id = execution.n8n_execution_id or x_codestra_execution
    execution.updated_at = datetime.now(UTC)
    if mapped in {
        ExecutionStatus.COMPLETED,
        ExecutionStatus.FAILED,
        ExecutionStatus.DEAD_LETTER,
    }:
        execution.completed_at = datetime.now(UTC)
    db.add(
        N8nRuntimeResult(
            result_id=uuid4(),
            execution_id=execution.execution_id,
            tenant_id=execution.tenant_id,
            workflow_code=execution.workflow_code,
            result_hash=result_hash,
            status=mapped,
            result_json=body.model_dump(mode="json"),
            occurred_at=body.occurred_at,
        )
    )
    db.add(
        AuditEvent(
            action="n8n.runtime.result",
            subject=str(execution.execution_id),
            correlation_id=execution.correlation_id,
            decision=mapped,
            redacted_payload={
                "tenant_id": execution.tenant_id,
                "result_hash": result_hash,
            },
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "n8n result conflict") from exc
    N8N_RESULT.labels(status=mapped).inc()
    return {
        "accepted": True,
        "duplicate": False,
        "execution_id": str(execution.execution_id),
        "status": mapped,
    }
