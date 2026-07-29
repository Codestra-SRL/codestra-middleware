"""Protected read/resolve surface for the generic event schema registry."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.events import _generic_authenticate
from app.core.config import settings
from app.db.models import IntegrationEventType
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/schemas", tags=["schema-registry"])
internal_router = APIRouter(prefix="/api/v1/internal/schemas", tags=["schema-registry"])


@router.get("/events/{event_type}/versions/{schema_version}")
async def read_event_schema(
    event_type: str,
    schema_version: str,
    authorization: Annotated[str, Header(alias="Authorization")],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    await _generic_authenticate(authorization, expected_environment=settings.environment, scope="integration.schema.read")
    row = await db.scalar(
        select(IntegrationEventType).where(
            IntegrationEventType.event_type == event_type,
            IntegrationEventType.schema_version == schema_version,
            IntegrationEventType.active.is_(True),
            IntegrationEventType.kill_switch.is_(False),
        )
    )
    if row is None:
        raise HTTPException(422, "EVENT_TYPE_UNSUPPORTED")
    return {
        "schema_version": row.schema_version,
        "event_type": row.event_type,
        "producer_service": row.producer_service,
        "active": row.active,
        "effective_at": row.effective_at.isoformat(),
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


class ResolveSchemaRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=128)
    schema_version: str = Field(min_length=1, max_length=16)
    producer_service: str = Field(min_length=1, max_length=64)
    environment: str = Field(min_length=1, max_length=32)


@internal_router.post("/resolve", include_in_schema=False)
async def resolve_event_schema(
    body: ResolveSchemaRequest,
    authorization: Annotated[str, Header(alias="Authorization")],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    await _generic_authenticate(authorization, expected_environment=settings.environment, scope="integration.schema.resolve")
    if body.environment != settings.environment:
        raise HTTPException(403, "schema environment denied")
    rows = (
        await db.execute(
            select(IntegrationEventType).where(
                IntegrationEventType.event_type == body.event_type,
                IntegrationEventType.schema_version == body.schema_version,
                IntegrationEventType.producer_service == body.producer_service,
                IntegrationEventType.active.is_(True),
                IntegrationEventType.kill_switch.is_(False),
                IntegrationEventType.effective_at <= datetime.now(UTC),
            )
        )
    ).scalars().all()
    if len(rows) != 1:
        raise HTTPException(503 if rows else 422, "SCHEMA_BINDING_AMBIGUOUS" if rows else "EVENT_TYPE_UNSUPPORTED")
    return {"schema_id": str(rows[0].event_type_id), "event_type": body.event_type, "schema_version": body.schema_version, "producer_service": body.producer_service}
