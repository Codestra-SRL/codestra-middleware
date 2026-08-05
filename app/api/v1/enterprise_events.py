"""Tenant-scoped immutable enterprise event API."""

import json
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.identity import _identity
from app.core.enterprise_events import EnterpriseEventError, EventEnvelope, idempotency_hash
from app.core.iam import IAMAuthorizationError
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/events", tags=["enterprise-events"])


class EventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    aggregate_type: str = Field(min_length=1, max_length=96)
    aggregate_id: str = Field(min_length=1, max_length=128)
    aggregate_sequence: int = Field(ge=1)
    event_type: str = Field(min_length=3, max_length=128)
    schema_version: str = Field(min_length=1, max_length=32)
    payload: dict[str, object]
    occurred_at: datetime
    correlation_id: str = Field(min_length=1, max_length=128)
    causation_id: str | None = Field(default=None, max_length=128)


class ReplayRequest(BaseModel):
    reason: str = Field(min_length=8, max_length=512)


def _context(authorization: str, permission: str):
    identity = _identity(authorization)
    try:
        identity.require_permission(permission)
        UUID(identity.tenant_id)
        UUID(identity.workspace_id)
    except (IAMAuthorizationError, ValueError) as exc:
        raise HTTPException(403, "event scope denied") from exc
    return identity


@router.post("", status_code=202)
async def publish_event(
    body: EventRequest,
    authorization: str = Header("", alias="Authorization"),
    idempotency_key: str = Header("", alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_session),
):
    identity = _context(authorization, "event.publish")
    envelope = EventEnvelope(**body.model_dump())
    try:
        envelope.validate()
        key_hash = idempotency_hash(identity.tenant_id, identity.workspace_id, idempotency_key)
        internal_id = uuid4()
        await db.execute(
            text("""
                INSERT INTO enterprise_event (
                    id, event_id, tenant_id, workspace_id, aggregate_type, aggregate_id,
                    aggregate_sequence, event_type, schema_version, payload, metadata,
                    idempotency_key_hash, correlation_id, causation_id, occurred_at, recorded_by
                ) VALUES (
                    :id, :event_id, :tenant_id, :workspace_id, :aggregate_type, :aggregate_id,
                    :aggregate_sequence, :event_type, :schema_version, CAST(:payload AS jsonb),
                    '{}'::jsonb, :key_hash, :correlation_id, :causation_id, :occurred_at, :recorded_by
                )
            """),
            {
                "id": internal_id,
                **body.model_dump(exclude={"payload"}),
                "payload": json.dumps(body.payload, sort_keys=True, separators=(",", ":")),
                "tenant_id": UUID(identity.tenant_id),
                "workspace_id": UUID(identity.workspace_id),
                "key_hash": key_hash,
                "recorded_by": identity.subject,
            },
        )
        await db.commit()
    except EnterpriseEventError as exc:
        raise HTTPException(422, str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "duplicate event, sequence, or idempotency key") from exc
    return {"id": str(internal_id), "event_id": body.event_id, "status": "accepted"}


@router.get("")
async def list_events(
    authorization: str = Header("", alias="Authorization"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
):
    identity = _context(authorization, "event.read")
    rows = (await db.execute(
        text("""
            SELECT id, event_id, event_type, schema_version, aggregate_type, aggregate_id,
                   aggregate_sequence, correlation_id, occurred_at, recorded_at
            FROM enterprise_event
            WHERE tenant_id=:tenant_id AND workspace_id=:workspace_id
            ORDER BY recorded_at DESC, id DESC LIMIT :limit
        """),
        {"tenant_id": UUID(identity.tenant_id), "workspace_id": UUID(identity.workspace_id), "limit": limit},
    )).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/{event_id}")
async def get_event(
    event_id: UUID,
    authorization: str = Header("", alias="Authorization"),
    db: AsyncSession = Depends(get_session),
):
    identity = _context(authorization, "event.read")
    row = (await db.execute(
        text("SELECT * FROM enterprise_event WHERE id=:id AND tenant_id=:tenant_id AND workspace_id=:workspace_id"),
        {"id": event_id, "tenant_id": UUID(identity.tenant_id), "workspace_id": UUID(identity.workspace_id)},
    )).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "event not found")
    return dict(row)


@router.post("/{event_id}/replay", status_code=202)
async def replay_event(
    event_id: UUID,
    body: ReplayRequest,
    authorization: str = Header("", alias="Authorization"),
    db: AsyncSession = Depends(get_session),
):
    identity = _context(authorization, "event.replay")
    result = await db.execute(
        text("""
            INSERT INTO enterprise_event_replay (
                id, event_id, tenant_id, workspace_id, requested_by, reason, status
            )
            SELECT :replay_id, id, tenant_id, workspace_id, :requested_by, :reason, 'PENDING'
            FROM enterprise_event
            WHERE id=:event_id AND tenant_id=:tenant_id AND workspace_id=:workspace_id
            RETURNING id
        """),
        {
            "replay_id": uuid4(), "event_id": event_id, "tenant_id": UUID(identity.tenant_id),
            "workspace_id": UUID(identity.workspace_id), "requested_by": identity.subject, "reason": body.reason,
        },
    )
    replay_id = result.scalar_one_or_none()
    if replay_id is None:
        await db.rollback()
        raise HTTPException(404, "event not found")
    await db.commit()
    return {"replay_id": str(replay_id), "status": "PENDING"}
