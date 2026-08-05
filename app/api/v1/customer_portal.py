from typing import Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.customer_portal import require_customer_feature, require_customer_scope
from app.db.models import CustomerAccount, CustomerUser
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/customer", tags=["customer-portal"])


async def _scope(tenant_id: str = Header("", alias="X-Customer-Tenant-ID"), role: str = Header("", alias="X-Customer-Role")) -> tuple[str, str]:
    return require_customer_scope(tenant_id, role)


@router.get("/me")
async def me(scope: tuple[str, str] = Depends(_scope), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_customer_feature(settings.customer_portal_enabled)
    tenant_id, role = scope
    user = await db.scalar(select(CustomerUser).where(CustomerUser.tenant_id == tenant_id, CustomerUser.status == "ACTIVE").limit(1))
    return {"tenant_id": tenant_id, "role": role, "user": {"id": str(user.id), "email": user.email, "display_name": user.display_name} if user else None}


@router.get("/company")
async def company(scope: tuple[str, str] = Depends(_scope), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_customer_feature(settings.customer_portal_enabled)
    tenant_id, _ = scope
    account = await db.scalar(select(CustomerAccount).where(CustomerAccount.tenant_id == tenant_id))
    if not account:
        return {"tenant_id": tenant_id, "status": "NOT_PROVISIONED"}
    return {"tenant_id": account.tenant_id, "workspace_id": account.workspace_id, "odoo_partner_id": account.odoo_partner_id, "status": account.status, "allowed_modules": account.allowed_modules}


@router.get("/users")
async def users(scope: tuple[str, str] = Depends(_scope), db: AsyncSession = Depends(get_session), limit: int = 50) -> dict[str, Any]:
    require_customer_feature(settings.customer_portal_enabled)
    tenant_id, _ = scope
    rows = (await db.scalars(select(CustomerUser).where(CustomerUser.tenant_id == tenant_id).order_by(CustomerUser.created_at.desc()).limit(min(limit, 100)))).all()
    return {"items": [{"id": str(row.id), "email": row.email, "display_name": row.display_name, "role": row.role, "status": row.status} for row in rows]}


@router.get("/{resource}")
async def customer_resource(resource: str, scope: tuple[str, str] = Depends(_scope)) -> dict[str, Any]:
    require_customer_feature(settings.customer_portal_enabled)
    if resource not in {"leads", "opportunities", "calls", "tickets", "projects", "documents", "invoices", "payments", "reports", "notifications", "activities", "appointments", "ai-insights"}:
        return {"items": []}
    return {"items": [], "tenant_id": scope[0], "status": "CONNECTED_READ_MODEL_PENDING"}
