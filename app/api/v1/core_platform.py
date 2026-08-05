"""Enterprise foundation and middleware control-plane APIs."""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.middleware_contracts import ScopeContext, command_allowed, event_allowed, valid_idempotency, valid_scope

router = APIRouter(prefix="/api/v1/core", tags=["enterprise-core"])


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_type: str = Field(min_length=1, max_length=96)
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class EventRequest(CommandRequest):
    event_type: str = Field(min_length=1, max_length=128)
    schema_version: str = Field(default="1.0", min_length=1, max_length=32)


def _scope(body: CommandRequest) -> ScopeContext:
    return ScopeContext(body.tenant_id, body.workspace_id, body.actor_id, body.correlation_id, body.trace_id)


@router.get("/health")
async def core_health() -> dict[str, Any]:
    return {
        "foundation": "ENABLED" if settings.enterprise_foundation_enabled else "DISABLED",
        "middleware": "ENABLED" if settings.middleware_platform_enabled else "DISABLED",
        "mutations": settings.core_mutations_enabled,
        "event_ingestion": settings.core_event_ingestion_enabled,
    }


@router.get("/services")
async def services() -> dict[str, Any]:
    if not settings.enterprise_foundation_enabled:
        raise HTTPException(404, "enterprise foundation unavailable")
    return {"services": [], "source": "authoritative-registry", "external_calls": False}


@router.post("/commands", status_code=202)
async def submit_command(body: CommandRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
    if not settings.middleware_platform_enabled:
        raise HTTPException(404, "middleware platform unavailable")
    if not valid_scope(_scope(body)) or not valid_idempotency(idempotency_key):
        raise HTTPException(400, "scope and idempotency are required")
    allowed, reason = command_allowed(mutations_enabled=settings.core_mutations_enabled)
    if not allowed:
        raise HTTPException(403, reason)
    return {"state": "QUEUED", "command_type": body.command_type, "idempotency_key": idempotency_key, "adapter_called": False}


@router.post("/events", status_code=202)
async def publish_event(body: EventRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> dict[str, Any]:
    if not settings.middleware_platform_enabled:
        raise HTTPException(404, "middleware platform unavailable")
    if not valid_scope(_scope(body)) or not valid_idempotency(idempotency_key):
        raise HTTPException(400, "scope and idempotency are required")
    allowed, reason = event_allowed(event_ingestion_enabled=settings.core_event_ingestion_enabled)
    if not allowed:
        raise HTTPException(403, reason)
    return {"state": "PUBLISHED", "event_type": body.event_type, "schema_version": body.schema_version, "idempotency_key": idempotency_key}
