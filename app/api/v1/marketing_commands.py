"""Durable, tenant-bound intake for governed Marketing activation commands."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.jwt_auth import JWTAuthError, KeycloakValidator
from app.db.models import AuditEvent, EventInbox, IdempotencyRecord, OutboxEvent
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/control/marketing", tags=["marketing-control"])


class ActivationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    campaign_id: UUID
    action: Literal["activate"] = "activate"
    expected_state: Literal["approved"] = "approved"
    expected_version: int = Field(ge=1)
    tenant_id: str
    correlation_id: str


class TransitionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID
    campaign_id: UUID
    action: Literal["pause", "resume"]
    expected_state: Literal["paused", "approved"]
    expected_version: int = Field(ge=1)
    tenant_id: str
    correlation_id: str


def _authenticate(authorization: str, tenant_id: str, required_scope: str) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = KeycloakValidator(
            issuer=settings.marketing_service_issuer,
            audience=settings.marketing_service_audience,
            jwks_url=settings.marketing_service_jwks_url,
            authorized_parties=frozenset({settings.marketing_service_client_id}),
            required_scopes=frozenset({required_scope}),
            required_environment="production",
        ).validate(authorization.removeprefix("Bearer ").strip())
    except JWTAuthError as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "invalid service token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    tenants = claims.get("tenants", [])
    if isinstance(tenants, str):
        tenants = tenants.replace(",", " ").split()
    if claims.get("tenant_id") != tenant_id and tenant_id not in set(tenants or []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant denied")
    return claims


def _request_hash(command: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(command.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def _create_campaign_command(
    command: ActivationCommand | TransitionCommand,
    response: Response,
    authorization: Annotated[str, Header(alias="Authorization")],
    tenant_id: Annotated[str, Header(alias="X-Tenant-ID", min_length=1, max_length=64)],
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=128)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=255)],
    db: Annotated[AsyncSession, Depends(get_session)],
    *,
    required_scope: str,
) -> dict[str, Any]:
    claims = _authenticate(authorization, tenant_id, required_scope)
    if command.tenant_id != tenant_id or command.correlation_id != correlation_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "command context mismatch")
    if idempotency_key != str(command.operation_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "operation idempotency binding mismatch")

    scope = f"marketing-{command.action}:{tenant_id}"
    key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
    request_hash = _request_hash(command)
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
    if prior is not None:
        if prior.request_hash != request_hash:
            await db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "idempotency key conflict")
        response.status_code = status.HTTP_200_OK
        response.headers["X-Correlation-ID"] = correlation_id
        return {**prior.response, "duplicate": True}

    if not settings.marketing_command_intake_enabled:
        await db.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "marketing command intake disabled")

    operation_id = str(command.operation_id)
    result = {
        "operation_id": operation_id,
        "state": "pending",
        "correlation_id": correlation_id,
        "duplicate": False,
    }
    payload = command.model_dump(mode="json")
    db.add(
        EventInbox(
            event_id=operation_id,
            source="marketing",
            event_type=f"marketing.campaign.{command.action}_requested",
            payload=payload,
            correlation_id=correlation_id,
            status="accepted",
        )
    )
    db.add(
        OutboxEvent(
            topic=f"marketing.campaign.{command.action}_requested",
            payload=payload,
            correlation_id=correlation_id,
            status="pending",
        )
    )
    db.add(
        IdempotencyRecord(
            scope=scope,
            key_hash=key_hash,
            request_hash=request_hash,
            response=result,
            status_code=status.HTTP_202_ACCEPTED,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
    )
    db.add(
        AuditEvent(
            action=f"marketing.campaign.{command.action}.accepted",
            subject=operation_id,
            correlation_id=correlation_id,
            decision="accepted",
            redacted_payload={
                "tenant_id": tenant_id,
                "campaign_id": str(command.campaign_id),
                "client_id": str(claims.get("azp", "")),
            },
        )
    )
    await db.commit()
    response.headers["X-Correlation-ID"] = correlation_id
    return result


@router.post("/campaign-activations", status_code=status.HTTP_202_ACCEPTED)
async def create_campaign_activation(
    command: ActivationCommand,
    response: Response,
    authorization: Annotated[str, Header(alias="Authorization")],
    tenant_id: Annotated[str, Header(alias="X-Tenant-ID", min_length=1, max_length=64)],
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=128)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=255)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    return await _create_campaign_command(
        command, response, authorization, tenant_id, correlation_id, idempotency_key, db,
        required_scope="marketing.activate",
    )


@router.post("/campaign-transitions", status_code=status.HTTP_202_ACCEPTED)
async def create_campaign_transition(
    command: TransitionCommand,
    response: Response,
    authorization: Annotated[str, Header(alias="Authorization")],
    tenant_id: Annotated[str, Header(alias="X-Tenant-ID", min_length=1, max_length=64)],
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=128)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=16, max_length=255)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    expected = "paused" if command.action == "pause" else "approved"
    if command.expected_state != expected:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "transition state mismatch")
    return await _create_campaign_command(
        command, response, authorization, tenant_id, correlation_id, idempotency_key, db,
        required_scope="marketing.transition",
    )
