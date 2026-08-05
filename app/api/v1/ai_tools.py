from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.ai_tool_gateway import ToolRequest, validate_request
from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai-workforce", tags=["ai-tools"])


@router.get("/tools")
async def tools(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.ai_tool_framework_enabled:
        raise HTTPException(404, "Tool framework unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "tools": [], "production_autonomy": False, "shell_execution": False}


@router.post("/tool-requests")
async def create_tool_request(request: ToolRequest) -> dict[str, Any]:
    if not settings.ai_tool_framework_enabled:
        raise HTTPException(404, "Tool framework unavailable")
    valid, reason = validate_request(request)
    if not valid:
        raise HTTPException(403, reason)
    return {"state": "WAITING_FOR_APPROVAL" if request.approval_required else "QUEUED", "adapter_called": False, "trace_id": request.trace_id}
