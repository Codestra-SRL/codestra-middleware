from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.voice_ai import CallAuthorization, authorize_outbound, VoicePolicyError
from app.db.models import VoiceSession, VoiceCallbackRequest
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/voice", tags=["voice-ai"])


def require_voice(tenant_id: str, role: str) -> None:
    if not tenant_id or not role:
        raise HTTPException(403, "voice authorization required")
    if not settings.voice_ai_platform_enabled:
        raise HTTPException(404, "Voice AI unavailable")


@router.post("/sessions", status_code=202)
async def create_session(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_voice(tenant_id, role)
    session = VoiceSession(tenant_id=tenant_id, workspace_id=str(body.get("workspace_id", "")), campaign_code=str(body.get("campaign_code", "")), direction=str(body.get("direction", "INBOUND")), status="REQUESTED", correlation_id=str(body.get("correlation_id", uuid4())), idempotency_key=str(body.get("idempotency_key", uuid4())))
    db.add(session)
    await db.commit()
    return {"session_id": str(session.id), "status": session.status}


@router.post("/sessions/{session_id}/authorize", status_code=202)
async def authorize(session_id: str, body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_voice(tenant_id, role)
    session = await db.scalar(select(VoiceSession).where(VoiceSession.id == session_id, VoiceSession.tenant_id == tenant_id))
    if not session:
        raise HTTPException(404, "voice session not found")
    try:
        allowed = authorize_outbound(CallAuthorization(tenant_id=tenant_id, campaign_code=session.campaign_code, phone=str(body.get("phone", "")), approved_number=bool(body.get("approved_number", False)), suppressed=bool(body.get("suppressed", False)), do_not_call=bool(body.get("do_not_call", False)), within_calling_window=bool(body.get("within_calling_window", False)), attempts=int(body.get("attempts", 0)), maximum_attempts=int(body.get("maximum_attempts", 1)), outbound_enabled=settings.voice_ai_outbound_enabled, emergency_stop=not settings.voice_ai_real_calls_enabled))
    except (VoicePolicyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    session.status = "AUTHORIZED" if allowed else "POLICY_BLOCKED"
    await db.commit()
    return {"session_id": session_id, "status": session.status, "dialing": False}


@router.post("/sessions/{session_id}/callback", status_code=202)
async def callback(session_id: str, body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_voice(tenant_id, role)
    request = VoiceCallbackRequest(session_id=session_id, tenant_id=tenant_id, phone=str(body.get("phone", "")), scheduled_at=str(body.get("scheduled_at", "")), idempotency_key=str(body.get("idempotency_key", uuid4())), status="REQUESTED")
    db.add(request)
    await db.commit()
    return {"callback_id": str(request.id), "status": request.status}
