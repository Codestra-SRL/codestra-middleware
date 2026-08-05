"""Integration registry, webhook, and connector gateway endpoints."""

from typing import Any
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.core.config import settings
from app.core.integration_platform import authorize_capability

router = APIRouter(prefix="/api/v1/integrations", tags=["integration-platform"])


class IntegrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connector_code: str = Field(min_length=1, max_length=96)
    capability: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    permission_granted: bool = False
    approval_granted: bool = False


@router.get("/connectors")
async def connectors(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.enterprise_integration_platform_enabled:
        raise HTTPException(404, "integration platform unavailable")
    if not tenant_id:
        raise HTTPException(403, "tenant scope required")
    return {"tenant_id": tenant_id, "connectors": [], "real_connections": False}


@router.post("/requests", status_code=202)
async def request_integration(body: IntegrationRequest) -> dict[str, Any]:
    if not settings.integration_staging_enabled:
        raise HTTPException(404, "integration staging unavailable")
    allowed, reason = authorize_capability(tenant_id=body.tenant_id, workspace_id=body.workspace_id, permission_granted=body.permission_granted, approval_granted=body.approval_granted, production_enabled=settings.real_connector_connections_enabled)
    if not allowed:
        raise HTTPException(403, reason)
    return {"state": "QUEUED", "connector_code": body.connector_code, "adapter_called": False}
