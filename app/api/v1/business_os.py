from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.business_os import CommandRequest, validate_command
from app.core.config import settings

router = APIRouter(prefix="/api/v1/business-os", tags=["business-os"])


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.business_os_enabled:
        raise HTTPException(404, "Business Operating System unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "graph": "scoped", "command_bar": True, "unified_writes": False}


@router.post("/commands")
async def command(request: CommandRequest) -> dict[str, Any]:
    if not settings.business_os_enabled:
        raise HTTPException(404, "Business Operating System unavailable")
    valid, reason = validate_command(request)
    if not valid:
        raise HTTPException(403, reason)
    return {"state": "ACCEPTED", "executed": False, "action": request.action, "tenant_id": request.tenant_id}
