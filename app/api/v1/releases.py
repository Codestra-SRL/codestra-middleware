from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.core.release_management import ReleaseReadiness, authorize_release

router = APIRouter(prefix="/api/v1/releases", tags=["releases"])


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.release_management_enabled:
        raise HTTPException(404, "Release platform unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "releases": [], "production_deployment": False}


@router.post("/readiness")
async def readiness(request: ReleaseReadiness) -> dict[str, str]:
    if not settings.release_management_enabled:
        raise HTTPException(404, "Release platform unavailable")
    valid, reason = authorize_release(request)
    if not valid:
        raise HTTPException(403, reason)
    return {"status": "READY_FOR_REVIEW", "production": "DISABLED"}
