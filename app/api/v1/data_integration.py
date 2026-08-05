from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from app.core.data_integration import ConnectorRequest, authorize_connector

router = APIRouter(prefix="/api/v1/enterprise", tags=["enterprise-data-integration"])


@router.get("/data/overview")
async def data_overview(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.enterprise_data_platform_enabled:
        raise HTTPException(404, "Enterprise data platform unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "catalog": "scoped", "external_exports": False}


@router.post("/integrations/requests")
async def connector_request(request: ConnectorRequest) -> dict[str, Any]:
    if not settings.integration_platform_enabled:
        raise HTTPException(404, "Integration platform unavailable")
    valid, reason = authorize_connector(request)
    if not valid:
        raise HTTPException(403, reason)
    return {"state": "SANDBOX", "adapter_called": False, "connector": request.connector_code}
