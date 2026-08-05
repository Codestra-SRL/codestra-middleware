from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.developer_platform import validate_scopes, DeveloperPlatformError
from app.db.models import DeveloperApplication, DeveloperWebhookSubscription, DeveloperSandbox
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/developer", tags=["developer-platform"])


def require_developer(role: str) -> None:
    if role not in {"DEVELOPER_ADMIN", "SAAS_ADMIN", "CUSTOMER_OWNER", "CUSTOMER_ADMIN"}:
        raise HTTPException(403, "developer platform authorization required")
    if not settings.developer_platform_enabled:
        raise HTTPException(404, "developer platform unavailable")


@router.get("/applications")
async def applications(role: str = Header("", alias="X-Codestra-Role"), tenant_id: str = Header("", alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_developer(role)
    if role.startswith("CUSTOMER") and not tenant_id:
        raise HTTPException(403, "tenant scope required")
    rows = (await db.scalars(select(DeveloperApplication).where(DeveloperApplication.tenant_id == tenant_id).limit(100))).all()
    return {"items": [{"id": str(a.id), "name": a.name, "status": a.status, "scopes": a.scopes} for a in rows]}


@router.post("/applications", status_code=202)
async def create_application(body: dict[str, Any], role: str = Header("", alias="X-Codestra-Role"), tenant_id: str = Header("", alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_developer(role)
    if not tenant_id:
        raise HTTPException(422, "tenant scope required")
    try:
        scopes = validate_scopes(list(body.get("scopes", [])))
    except DeveloperPlatformError as exc:
        raise HTTPException(422, str(exc)) from exc
    app = DeveloperApplication(tenant_id=tenant_id, name=str(body.get("name", "")).strip(), client_type=str(body.get("client_type", "CONFIDENTIAL")), scopes=list(scopes), status="ACTIVE", correlation_id=str(body.get("correlation_id", uuid4())))
    if not app.name:
        raise HTTPException(422, "application name required")
    db.add(app)
    await db.commit()
    return {"application_id": str(app.id), "status": app.status, "scopes": app.scopes, "secret_returned": False}


@router.post("/webhooks", status_code=202)
async def create_webhook(body: dict[str, Any], role: str = Header("", alias="X-Codestra-Role"), tenant_id: str = Header("", alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_developer(role)
    event = str(body.get("event_type", ""))
    if event not in {"lead.created", "lead.updated", "call.completed", "ticket.created", "invoice.paid", "project.updated", "subscription.updated"}:
        raise HTTPException(422, "unsupported webhook event")
    hook = DeveloperWebhookSubscription(tenant_id=tenant_id, event_type=event, endpoint_url=str(body.get("endpoint_url", "")), status="ACTIVE", secret_reference="pending-secret-reference")
    db.add(hook)
    await db.commit()
    return {"webhook_id": str(hook.id), "status": hook.status, "secret_returned": False}


@router.post("/sandboxes", status_code=202)
async def create_sandbox(role: str = Header("", alias="X-Codestra-Role"), tenant_id: str = Header("", alias="X-Tenant-ID"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_developer(role)
    sandbox = DeveloperSandbox(tenant_id=tenant_id, status="PROVISIONING", environment="sandbox", idempotency_key=str(uuid4()))
    db.add(sandbox)
    await db.commit()
    return {"sandbox_id": str(sandbox.id), "status": sandbox.status, "production_data": False}
