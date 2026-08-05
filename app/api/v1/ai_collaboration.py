from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.ai_collaboration import DelegationRequest, authorize_delegation
from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai-workforce", tags=["ai-collaboration"])


@router.get("/departments")
async def departments(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.ai_department_platform_enabled:
        raise HTTPException(404, "Department platform unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "departments": [], "production_autonomy": False}


@router.post("/collaborations/{collaboration_id}/delegate")
async def delegate(collaboration_id: str, request: DelegationRequest) -> dict[str, Any]:
    if not settings.ai_collaboration_enabled:
        raise HTTPException(404, "Collaboration unavailable")
    valid, reason = authorize_delegation(request)
    if not valid:
        raise HTTPException(403, reason)
    return {"collaboration_id": collaboration_id, "state": "WAITING_FOR_ACCEPTANCE", "created": False}
