"""Tenant-bound compatibility operations for the governed n8n runtime.

These routes are deliberately thin views and control requests over
``N8nRuntimeExecution``. They do not dispatch workflows or duplicate the n8n
runtime worker's retry and timeout policy.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.jwt_auth import JWTAuthError, KeycloakValidator
from app.core.n8n_runtime import ExecutionStatus, TERMINAL_STATUSES
from app.db.models import AuditEvent, IdempotencyRecord, N8nRuntimeExecution
from app.db.session import get_session

router = APIRouter(prefix="/v1/integrations/n8n/operations", tags=["n8n-operations"])


def _authenticate(authorization: str, tenant_id: str, required_scope: str) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer token required")
    try:
        claims = KeycloakValidator(
            issuer=settings.n8n_service_issuer,
            audience=settings.n8n_service_audience,
            jwks_url=settings.n8n_service_jwks_url,
            authorized_parties=frozenset({settings.n8n_service_client_id}),
            required_scopes=frozenset({required_scope}),
            required_environment="production",
        ).validate(authorization.removeprefix("Bearer ").strip())
    except JWTAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    tenants = claims.get("tenants", [])
    if isinstance(tenants, str):
        tenants = tenants.replace(",", " ").split()
    if claims.get("tenant_id") != tenant_id and tenant_id not in set(tenants or []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant denied")
    return claims


def _safe(value: N8nRuntimeExecution) -> dict[str, Any]:
    return {
        "operation_id": str(value.execution_id),
        "tenant_id": value.tenant_id,
        "state": str(value.status),
        "workflow_code": value.workflow_code,
        "workflow_version": value.workflow_version,
        "correlation_id": value.correlation_id,
        "attempt_count": value.attempt_count,
        "timeout_at": value.timeout_at.isoformat(),
        "created_at": value.created_at.isoformat(),
        "updated_at": value.updated_at.isoformat(),
        "completed_at": value.completed_at.isoformat() if value.completed_at else None,
        "failure_class": value.failure_class,
        "last_error_code": value.last_error_code,
    }


@router.get("")
async def list_operations(
    response: Response,
    authorization: Annotated[str, Header(alias="Authorization")],
    tenant_id: Annotated[str, Header(alias="X-Tenant-ID", min_length=1, max_length=64)],
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=128)],
    db: Annotated[AsyncSession, Depends(get_session)],
    operation_state: ExecutionStatus | None = Query(default=None, alias="state"),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    _authenticate(authorization, tenant_id, "n8n.operations.read")
    query = select(N8nRuntimeExecution).where(N8nRuntimeExecution.tenant_id == tenant_id)
    if operation_state is not None:
        query = query.where(N8nRuntimeExecution.status == operation_state)
    rows = (
        await db.scalars(
            query.order_by(
                N8nRuntimeExecution.created_at.desc(),
                N8nRuntimeExecution.execution_id.desc(),
            ).limit(limit)
        )
    ).all()
    response.headers["X-Correlation-ID"] = correlation_id
    return {
        "items": [_safe(row) for row in rows],
        "count": len(rows),
        "correlation_id": correlation_id,
    }


async def _reserve_mutation(
    *,
    db: AsyncSession,
    action: str,
    operation_id: UUID,
    tenant_id: str,
    idempotency_key: str,
) -> tuple[IdempotencyRecord | None, str, str]:
    scope = f"n8n-operation:{tenant_id}:{action}"
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    request_hash = hashlib.sha256(
        json.dumps(
            {"action": action, "operation_id": str(operation_id), "tenant_id": tenant_id},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
        {"scope": f"{scope}:{key_hash}"},
    )
    prior = await db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key_hash == key_hash,
        )
    )
    if prior is not None and prior.request_hash != request_hash:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "idempotency key conflict")
    return prior, scope, request_hash


async def _operation_for_update(
    db: AsyncSession, operation_id: UUID, tenant_id: str
) -> N8nRuntimeExecution:
    operation = await db.get(N8nRuntimeExecution, operation_id, with_for_update=True)
    if operation is None or operation.tenant_id != tenant_id:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "operation not found")
    return operation


def _store_control_evidence(
    *,
    db: AsyncSession,
    scope: str,
    request_hash: str,
    idempotency_key: str,
    response: dict[str, Any],
    action: str,
    operation: N8nRuntimeExecution,
    prior_state: str,
    correlation_id: str,
) -> None:
    db.add(
        IdempotencyRecord(
            scope=scope,
            key_hash=hashlib.sha256(idempotency_key.encode()).hexdigest(),
            request_hash=request_hash,
            response=response,
            status_code=status.HTTP_202_ACCEPTED,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    db.add(
        AuditEvent(
            action=f"n8n.operation.{action}",
            subject=str(operation.execution_id),
            correlation_id=correlation_id,
            decision="accepted",
            redacted_payload={
                "tenant_id": operation.tenant_id,
                "prior_state": prior_state,
            },
        )
    )


@router.post("/{operation_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_operation(
    operation_id: UUID,
    response: Response,
    authorization: Annotated[str, Header(alias="Authorization")],
    tenant_id: Annotated[str, Header(alias="X-Tenant-ID", min_length=1, max_length=64)],
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=128)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=255)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    _authenticate(authorization, tenant_id, "n8n.operations.cancel")
    prior, scope, request_hash = await _reserve_mutation(
        db=db,
        action="cancel",
        operation_id=operation_id,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
    )
    if prior is not None:
        response.status_code = status.HTTP_200_OK
        return {**prior.response, "duplicate": True}
    operation = await _operation_for_update(db, operation_id, tenant_id)
    if operation.status not in {ExecutionStatus.PENDING, ExecutionStatus.RETRY}:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "operation can no longer be cancelled without downstream confirmation",
        )
    prior_state = str(operation.status)
    operation.status = ExecutionStatus.CANCELLED
    operation.completed_at = datetime.now(UTC)
    operation.updated_at = operation.completed_at
    operation.next_attempt_at = None
    result = {
        "operation_id": str(operation.execution_id),
        "state": str(operation.status),
        "prior_state": prior_state,
        "correlation_id": correlation_id,
        "duplicate": False,
    }
    _store_control_evidence(
        db=db,
        scope=scope,
        request_hash=request_hash,
        idempotency_key=idempotency_key,
        response=result,
        action="cancelled",
        operation=operation,
        prior_state=prior_state,
        correlation_id=correlation_id,
    )
    await db.commit()
    response.headers["X-Correlation-ID"] = correlation_id
    return result


@router.post("/{operation_id}/reconcile", status_code=status.HTTP_202_ACCEPTED)
async def reconcile_operation(
    operation_id: UUID,
    response: Response,
    authorization: Annotated[str, Header(alias="Authorization")],
    tenant_id: Annotated[str, Header(alias="X-Tenant-ID", min_length=1, max_length=64)],
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=128)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=255)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    _authenticate(authorization, tenant_id, "n8n.operations.reconcile")
    prior, scope, request_hash = await _reserve_mutation(
        db=db,
        action="reconcile",
        operation_id=operation_id,
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
    )
    if prior is not None:
        response.status_code = status.HTTP_200_OK
        return {**prior.response, "duplicate": True}
    operation = await _operation_for_update(db, operation_id, tenant_id)
    if operation.status in TERMINAL_STATUSES:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "terminal operation requires authenticated downstream read-back before retry",
        )
    result = {
        "operation_id": str(operation.execution_id),
        "state": str(operation.status),
        "reconciliation_state": "recorded",
        "correlation_id": correlation_id,
        "duplicate": False,
    }
    _store_control_evidence(
        db=db,
        scope=scope,
        request_hash=request_hash,
        idempotency_key=idempotency_key,
        response=result,
        action="reconciliation_requested",
        operation=operation,
        prior_state=str(operation.status),
        correlation_id=correlation_id,
    )
    await db.commit()
    response.headers["X-Correlation-ID"] = correlation_id
    return result
