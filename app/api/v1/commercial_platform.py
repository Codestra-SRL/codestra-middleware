"""Commercial provisioning, usage, and SLA staging endpoints."""

from typing import Any
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.core.commercial_platform import ProvisioningRequest, provisioning_key
from app.core.config import settings

router = APIRouter(prefix="/api/v1/commercial-platform", tags=["commercial-platform"])


class ProvisioningBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    subscription_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=8, max_length=255)


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.commercial_platform_enabled:
        raise HTTPException(404, "commercial platform unavailable")
    if not tenant_id:
        raise HTTPException(403, "tenant scope required")
    return {"tenant_id": tenant_id, "payment_collection": False, "automatic_renewals": False, "subscriptions": []}


@router.post("/provisioning", status_code=202)
async def provision(body: ProvisioningBody) -> dict[str, Any]:
    if not settings.tenant_provisioning_staging_enabled:
        raise HTTPException(404, "tenant provisioning staging unavailable")
    request = ProvisioningRequest(**body.model_dump())
    return {"state": "PROVISIONING", "provisioning_key": provisioning_key(request), "external_writes": False}
