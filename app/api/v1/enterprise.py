from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings

router = APIRouter(prefix="/api/v1/enterprise", tags=["enterprise"])


def require_enterprise(tenant_id: str, role: str) -> None:
    if not tenant_id or not role:
        raise HTTPException(403, "enterprise authorization required")
    if not settings.enterprise_platform_enabled:
        raise HTTPException(404, "enterprise platform unavailable")


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_enterprise(tenant_id, role)
    return {"tenant_id": tenant_id, "phases": {"iam": "staging", "governance": "staging", "integrations": "staging", "data": "staging", "dr": "staging"}}
