from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.core.named_pilot import CustomerPilotPreconditions, evidence_complete

router = APIRouter(prefix="/api/v1/ai-workforce", tags=["named-pilot"])


@router.get("/named-pilots")
async def pilots(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.named_customer_pilot_framework_enabled:
        raise HTTPException(404, "Named pilot framework unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "pilots": [], "real_activation": False, "simulated_observation": True}


@router.post("/named-pilots/validate-evidence")
async def validate_evidence(preconditions: CustomerPilotPreconditions) -> dict[str, bool]:
    if not settings.named_customer_pilot_framework_enabled:
        raise HTTPException(404, "Named pilot framework unavailable")
    return {"evidence_complete": evidence_complete(preconditions), "real_activation": False}
