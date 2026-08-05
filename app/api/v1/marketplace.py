from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.marketplace import validate_manifest, ManifestError
from app.db.models import MarketplacePlugin, MarketplaceTenantInstallation
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/marketplace", tags=["marketplace"])


def require_marketplace(role: str) -> None:
    if role not in {"MARKETPLACE_ADMIN", "SAAS_ADMIN", "SAAS_AUDITOR", "CUSTOMER_OWNER", "CUSTOMER_ADMIN"}:
        raise HTTPException(403, "marketplace authorization required")
    if not settings.marketplace_enabled:
        raise HTTPException(404, "marketplace unavailable")


@router.get("/plugins")
async def plugins(role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_marketplace(role)
    rows = (await db.scalars(select(MarketplacePlugin).where(MarketplacePlugin.status.in_({"AVAILABLE", "PUBLISHED_STAGING"})).limit(100))).all()
    return {"items": [{"id": str(p.id), "plugin_code": p.plugin_code, "display_name": p.display_name, "plugin_type": p.plugin_type, "status": p.status} for p in rows]}


@router.post("/plugins/validate", status_code=202)
async def validate_plugin(body: dict[str, Any], role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_marketplace(role)
    try:
        manifest = validate_manifest(body)
    except ManifestError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"plugin_code": manifest.plugin_code, "version": manifest.version, "status": "VALIDATING", "requested_capabilities": manifest.requested_capabilities}


@router.post("/installations", status_code=202)
async def install(body: dict[str, Any], role: str = Header("", alias="X-Codestra-Role"), tenant_id: str = Header("", alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_marketplace(role)
    if role.startswith("CUSTOMER") and not tenant_id:
        raise HTTPException(403, "tenant scope required")
    if not settings.marketplace_customer_ui_enabled or not settings.marketplace_automatic_install_enabled:
        raise HTTPException(409, "installation requires approved controlled execution")
    key = str(body.get("idempotency_key", "")).strip()
    if not key:
        raise HTTPException(422, "idempotency_key required")
    existing = await db.scalar(select(MarketplaceTenantInstallation).where(MarketplaceTenantInstallation.tenant_id == tenant_id, MarketplaceTenantInstallation.idempotency_key == key))
    if existing:
        return {"installation_id": str(existing.id), "status": existing.status, "idempotent": True}
    installation = MarketplaceTenantInstallation(tenant_id=tenant_id, plugin_id=body.get("plugin_id"), version=body.get("version", ""), status="INSTALLING", idempotency_key=key, correlation_id=str(body.get("correlation_id", uuid4())))
    db.add(installation)
    await db.commit()
    return {"installation_id": str(installation.id), "status": installation.status, "idempotent": False}
