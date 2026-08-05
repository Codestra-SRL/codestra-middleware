from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings
from pydantic import BaseModel, ConfigDict, Field

from app.core.control_tower import EmergencyControl, ExecutiveAction, authorize_action, authorize_emergency_control

router = APIRouter(prefix="/api/v1/control-tower", tags=["control-tower"])


class EmergencyControlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    state: str = Field(min_length=1, max_length=32)
    scope: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=1000)
    privileged: bool = False
    mfa_verified: bool = False
    approved: bool = False
    idempotency_key: str = Field(min_length=1, max_length=160)
    automatic_reenable: bool = False


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.control_tower_enabled:
        raise HTTPException(404, "Control Tower unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "services": [], "freshness": "UNKNOWN", "autonomous_actions": False}


@router.post("/actions")
async def action(request: ExecutiveAction) -> dict[str, Any]:
    if not settings.governed_executive_actions_enabled:
        raise HTTPException(404, "Executive actions unavailable")
    valid, reason = authorize_action(request)
    if not valid:
        raise HTTPException(403, reason)
    return {"state": "APPROVED", "executed": False, "action": request.action}


@router.post("/emergency-controls", status_code=202)
async def emergency_control(request: EmergencyControlRequest) -> dict[str, Any]:
    """Record a governed emergency intent; it never changes runtime state here."""
    if not settings.governed_executive_actions_enabled:
        raise HTTPException(404, "Executive actions unavailable")
    valid, reason = authorize_emergency_control(EmergencyControl(**request.model_dump()))
    if not valid:
        raise HTTPException(403, reason)
    return {"state": "APPROVED", "executed": False, "automatic_reenable": False, "scope": request.scope}
