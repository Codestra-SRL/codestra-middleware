from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.mobile import validate_deep_link, MobileSecurityError
from app.db.models import MobileDevice, MobilePushToken, MobileSyncSession
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"])


def require_mobile(tenant_id: str, role: str) -> None:
    if not tenant_id or not role:
        raise HTTPException(403, "mobile tenant authentication required")
    if not settings.mobile_platform_enabled:
        raise HTTPException(404, "mobile platform unavailable")


@router.get("/bootstrap")
async def bootstrap(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Mobile-Role")) -> dict[str, Any]:
    require_mobile(tenant_id, role)
    return {"tenant_id": tenant_id, "role": role, "features": {"offline": settings.mobile_offline_mode_enabled, "ai": settings.mobile_ai_assistant_enabled, "recordings": settings.mobile_recording_access_enabled, "sip": settings.mobile_sip_calling_enabled}}


@router.post("/devices/register", status_code=202)
async def register_device(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Mobile-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_mobile(tenant_id, role)
    device = MobileDevice(tenant_id=tenant_id, user_reference=str(body.get("user_reference", "")), platform=str(body.get("platform", "")), device_hash=str(body.get("device_hash", "")), app_version=str(body.get("app_version", "")), status="PENDING")
    if not device.user_reference or not device.platform or not device.device_hash:
        raise HTTPException(422, "device fields required")
    db.add(device)
    await db.commit()
    return {"device_id": str(device.id), "status": device.status}


@router.post("/devices/{device_id}/revoke", status_code=202)
async def revoke_device(device_id: str, tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Mobile-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_mobile(tenant_id, role)
    device = await db.scalar(select(MobileDevice).where(MobileDevice.id == device_id, MobileDevice.tenant_id == tenant_id))
    if not device:
        raise HTTPException(404, "device not found")
    device.status = "REVOKED"
    await db.commit()
    return {"device_id": device_id, "status": device.status}


@router.post("/push-token", status_code=202)
async def push_token(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Mobile-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_mobile(tenant_id, role)
    token = MobilePushToken(tenant_id=tenant_id, device_id=body.get("device_id"), token_reference=str(body.get("token_reference", "")), platform=str(body.get("platform", "")), status="ACTIVE")
    if not token.token_reference:
        raise HTTPException(422, "token reference required")
    db.add(token)
    await db.commit()
    return {"push_token_id": str(token.id), "status": token.status}


@router.post("/sync", status_code=202)
async def sync(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Mobile-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_mobile(tenant_id, role)
    session = MobileSyncSession(tenant_id=tenant_id, client_session_id=str(body.get("client_session_id", uuid4())), status="PENDING", item_count=min(int(body.get("item_count", 0)), 100))
    db.add(session)
    await db.commit()
    return {"sync_session_id": str(session.id), "status": session.status}


@router.post("/deep-link/validate")
async def deep_link(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Mobile-Role")) -> dict[str, Any]:
    require_mobile(tenant_id, role)
    try:
        path = validate_deep_link(str(body.get("url", "")))
    except MobileSecurityError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"path": path, "tenant_id": tenant_id}
