from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.ai_pilot import PilotAdmission, authorize_admission
from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai-workforce", tags=["ai-pilot"])


@router.get("/pilots")
async def pilots(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.ai_workforce_pilot_enabled:
        raise HTTPException(404, "Pilot platform unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "pilots": [], "global_production": False}


@router.post("/pilot-admissions")
async def admit(admission: PilotAdmission) -> dict[str, Any]:
    if not settings.ai_workforce_pilot_enabled:
        raise HTTPException(404, "Pilot platform unavailable")
    valid, reason = authorize_admission(admission)
    if not valid:
        raise HTTPException(403, reason)
    return {"state": "READY_FOR_APPROVAL", "activated": False}
