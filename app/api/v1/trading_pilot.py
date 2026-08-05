from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings

router = APIRouter(prefix="/api/v1/trading/pilot", tags=["trading-pilot"])


@router.get("/readiness")
async def readiness(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    if not tenant_id or not role:
        raise HTTPException(403, "pilot authorization required")
    if not settings.trading_pilot_governance_enabled:
        raise HTTPException(404, "pilot governance unavailable")
    return {"tenant_id": tenant_id, "status": "REVIEW_REQUIRED", "live_trading": False, "funding": False, "custody": False}
