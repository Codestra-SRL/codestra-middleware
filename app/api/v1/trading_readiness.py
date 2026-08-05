from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings

router = APIRouter(prefix="/api/v1/trading/readiness", tags=["trading-readiness"])


def require_readiness(tenant_id: str, role: str) -> None:
    if not tenant_id or not role:
        raise HTTPException(403, "trading readiness authorization required")
    if not settings.trading_compliance_platform_enabled:
        raise HTTPException(404, "trading readiness unavailable")


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_readiness(tenant_id, role)
    return {"tenant_id": tenant_id, "sandbox": True, "live_broker": False, "real_money": False, "custody": False}
