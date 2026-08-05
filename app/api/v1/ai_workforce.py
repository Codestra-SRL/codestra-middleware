from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai-workforce", tags=["ai-workforce"])


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    if not tenant_id or not role:
        raise HTTPException(403, "AI Workforce authorization required")
    if not settings.ai_workforce_platform_enabled:
        raise HTTPException(404, "AI Workforce unavailable")
    return {"tenant_id": tenant_id, "status": "staging", "production_activation": False, "external_messages": False}
