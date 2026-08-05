from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.saas import PLAN_CONTRACTS, quota_outcome
from app.db.models import SaasAccount, SaasProvisioningRequest, SaasUsageEvent
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/saas", tags=["saas"])


def require_saas(role: str) -> None:
    if role not in {"SAAS_ADMIN", "SAAS_PROVISIONING_OPERATOR", "SAAS_BILLING_MANAGER", "SAAS_AUDITOR", "CUSTOMER_OWNER", "CUSTOMER_ADMIN"}:
        raise HTTPException(403, "SaaS authorization required")
    if not settings.saas_platform_enabled:
        raise HTTPException(404, "SaaS platform unavailable")


@router.get("/plans")
async def plans(role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_saas(role)
    return {"items": [{"code": p.code, "display_name": p.display_name, "entitlements": p.entitlements} for p in PLAN_CONTRACTS]}


@router.post("/provisioning", status_code=202)
async def create_provisioning(body: dict[str, Any], role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_saas(role)
    if not settings.saas_provisioning_enabled:
        raise HTTPException(404, "provisioning unavailable")
    key = str(body.get("idempotency_key", "")).strip()
    if not key or len(key) > 255:
        raise HTTPException(422, "idempotency_key required")
    existing = await db.scalar(select(SaasProvisioningRequest).where(SaasProvisioningRequest.idempotency_key == key))
    if existing:
        return {"request_id": str(existing.id), "status": existing.status, "idempotent": True}
    request = SaasProvisioningRequest(idempotency_key=key, onboarding_mode=str(body.get("onboarding_mode", "SALES_ASSISTED")), plan_code=str(body.get("plan_code", "STARTER")), status="REQUESTED", correlation_id=str(body.get("correlation_id", uuid4())), requested_by=role)
    db.add(request)
    await db.commit()
    return {"request_id": str(request.id), "status": request.status, "idempotent": False}


@router.get("/accounts")
async def accounts(role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_saas(role)
    rows = (await db.scalars(select(SaasAccount).order_by(SaasAccount.created_at.desc()).limit(100))).all()
    return {"items": [{"id": str(a.id), "tenant_id": a.tenant_id, "display_name": a.display_name, "status": a.status, "subscription_status": a.subscription_status} for a in rows]}


@router.get("/usage/{tenant_id}/{meter_code}")
async def usage(tenant_id: str, meter_code: str, allowance: int = 0, role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_saas(role)
    rows = (await db.scalars(select(SaasUsageEvent).where(SaasUsageEvent.tenant_id == tenant_id, SaasUsageEvent.meter_code == meter_code))).all()
    used = sum(row.quantity for row in rows)
    return {"tenant_id": tenant_id, "meter_code": meter_code, "used": used, "allowance": allowance, "outcome": quota_outcome(used, allowance)}
