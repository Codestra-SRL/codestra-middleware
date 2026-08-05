from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.support import SupportPolicyError, validate_priority, validate_ticket_state
from app.db.models import SupportConversation, SupportTicket
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/support", tags=["support"])


def require_support(tenant_id: str, role: str) -> None:
    if not tenant_id or not role:
        raise HTTPException(403, "support authorization required")
    if not settings.support_platform_enabled:
        raise HTTPException(404, "support platform unavailable")


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_support(tenant_id, role)
    return {"tenant_id": tenant_id, "status": "read_model_pending", "automatic_replies": False}


@router.post("/tickets", status_code=202)
async def create_ticket(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_support(tenant_id, role)
    try:
        state = validate_ticket_state(str(body.get("status", "NEW")))
        priority = validate_priority(str(body.get("priority", "NORMAL")))
    except SupportPolicyError as exc:
        raise HTTPException(422, str(exc)) from exc
    ticket = SupportTicket(tenant_id=tenant_id, customer_id=str(body.get("customer_id", "")), subject=str(body.get("subject", "")), status=state, priority=priority, idempotency_key=str(body.get("idempotency_key", uuid4())))
    if not ticket.customer_id or not ticket.subject:
        raise HTTPException(422, "customer_id and subject required")
    db.add(ticket)
    await db.commit()
    return {"ticket_id": str(ticket.id), "status": ticket.status, "priority": ticket.priority}


@router.post("/tickets/{ticket_id}/messages", status_code=202)
async def create_message(ticket_id: str, body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_support(tenant_id, role)
    message = SupportConversation(tenant_id=tenant_id, ticket_id=ticket_id, channel=str(body.get("channel", "INTERNAL")), status="PENDING_HUMAN_REVIEW", idempotency_key=str(body.get("idempotency_key", uuid4())))
    db.add(message)
    await db.commit()
    return {"message_id": str(message.id), "status": message.status}
