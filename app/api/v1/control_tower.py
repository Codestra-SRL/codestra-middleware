from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.core.control_tower import ExecutiveAction, authorize_action

router = APIRouter(prefix="/api/v1/control-tower", tags=["control-tower"])


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.control_tower_enabled:
        raise HTTPException(404, "Control Tower unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "services": [], "freshness": "UNKNOWN", "autonomous_actions": False}


@router.post("/actions")
async def action(request: ExecutiveAction) -> dict[str, Any]:
    if not settings.governed_executive_actions_enabled:
        raise HTTPException(404, "Executive actions unavailable")
    valid, reason = authorize_action(request)
    if not valid:
        raise HTTPException(403, reason)
    return {"state": "APPROVED", "executed": False, "action": request.action}
