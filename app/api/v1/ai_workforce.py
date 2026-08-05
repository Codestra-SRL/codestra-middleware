from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.core.ai_orchestration import DispatchRequest, authorize_dispatch, initial_task_state
from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai-workforce", tags=["ai-workforce"])


class DispatchIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = Field(min_length=1, max_length=128)
    employee_id: str = Field(min_length=1, max_length=128)
    department_id: str = Field(min_length=1, max_length=128)
    goal_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    workflow_code: str = Field(min_length=1, max_length=128)
    workflow_version: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=160)
    trace_id: str = Field(min_length=1, max_length=128)
    employee_active: bool = False
    department_active: bool = False
    goal_active: bool = False
    permission_granted: bool = False
    approval_required: bool = True
    approval_granted: bool = False
    workflow_approved: bool = False
    emergency_state: str = "CLEAR"


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    if not tenant_id or not role:
        raise HTTPException(403, "AI Workforce authorization required")
    if not settings.ai_workforce_platform_enabled:
        raise HTTPException(404, "AI Workforce unavailable")
    return {"tenant_id": tenant_id, "status": "staging", "production_activation": False, "external_messages": False}


@router.post("/dispatch", status_code=202)
async def dispatch(intent: DispatchIntent, tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    """Persistable dispatch decision; no n8n/Redis/adapter call is made here."""
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    if not settings.ai_workforce_platform_enabled:
        raise HTTPException(404, "AI Workforce unavailable")
    decision, reason = authorize_dispatch(DispatchRequest(tenant_id=tenant_id, **intent.model_dump()))
    if not decision:
        raise HTTPException(403, reason)
    return {
        "state": initial_task_state(approval_required=intent.approval_required, approval_granted=intent.approval_granted),
        "adapter_called": False,
        "outbox_published": False,
        "redis_published": False,
        "production_activation": False,
        "trace_id": intent.trace_id,
    }
