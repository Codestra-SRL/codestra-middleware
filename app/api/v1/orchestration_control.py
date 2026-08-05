"""Workflow orchestration and Redis-state policy endpoints."""

from typing import Any
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.core.config import settings
from app.core.orchestration_contracts import WorkflowContext, valid_workflow_context
from app.core.redis_state import RedisKeyContext, redis_key

router = APIRouter(prefix="/api/v1/orchestration", tags=["orchestration"])


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workflow_code: str = Field(min_length=1, max_length=128)
    workflow_version: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    command_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    trace_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=255)


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not tenant_id:
        raise HTTPException(403, "tenant scope required")
    return {"tenant_id": tenant_id, "postgresql_authoritative": True, "redis_authoritative": False, "n8n_external_execution": False}


@router.post("/workflows", status_code=202)
async def dispatch(body: WorkflowRequest) -> dict[str, Any]:
    if not settings.orchestration_platform_enabled:
        raise HTTPException(404, "orchestration platform unavailable")
    context = WorkflowContext(**body.model_dump())
    if not valid_workflow_context(context):
        raise HTTPException(400, "workflow context is incomplete")
    return {"state": "OUTBOX_PENDING", "workflow_code": body.workflow_code, "redis_published": False, "postgresql_authoritative": True}


@router.get("/redis/key")
async def key_preview(tenant_id: str = Header("", alias="X-Tenant-ID"), workspace_id: str = Header("", alias="X-Workspace-ID")) -> dict[str, str]:
    if not tenant_id or not workspace_id:
        raise HTTPException(403, "tenant and workspace scope required")
    return {"key": redis_key(RedisKeyContext("staging", tenant_id, workspace_id, "workflows", "queue", "core")), "secrets": "not_in_key"}
