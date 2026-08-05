from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.commercial import EntitlementRequest, decide_entitlement
from app.core.config import settings

router = APIRouter(prefix="/api/v1/commercial", tags=["commercial"])


@router.get("/plans")
async def plans(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.commercial_platform_enabled:
        raise HTTPException(404, "Commercial platform unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "plans": [], "real_payment_collection": False}


@router.post("/entitlements/check")
async def entitlement(request: EntitlementRequest) -> dict[str, str]:
    if not settings.entitlement_platform_enabled:
        raise HTTPException(404, "Entitlement platform unavailable")
    return {"decision": decide_entitlement(request)}
