from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.legal import LegalPolicyError, validate_intake_state
from app.db.models import LegalIntake, LegalMatter, LegalProspect
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/legal", tags=["legal"])


def require_legal(tenant_id: str, role: str) -> None:
    if not tenant_id or not role:
        raise HTTPException(403, "legal authorization required")
    if not settings.legal_platform_enabled:
        raise HTTPException(404, "legal platform unavailable")


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_legal(tenant_id, role)
    return {"tenant_id": tenant_id, "status": "read_model_pending", "automatic_conflict_clearance": False}


@router.post("/intakes", status_code=202)
async def create_intake(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_legal(tenant_id, role)
    try:
        state = validate_intake_state(str(body.get("status", "DRAFT")))
    except LegalPolicyError as exc:
        raise HTTPException(422, str(exc)) from exc
    prospect = LegalProspect(tenant_id=tenant_id, display_name=str(body.get("display_name", "")))
    if not prospect.display_name:
        raise HTTPException(422, "display_name required")
    db.add(prospect)
    await db.flush()
    intake = LegalIntake(tenant_id=tenant_id, prospect_id=str(prospect.id), status=state, idempotency_key=str(body.get("idempotency_key", uuid4())))
    db.add(intake)
    await db.commit()
    return {"intake_id": str(intake.id), "status": intake.status}


@router.post("/matters", status_code=202)
async def create_matter(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_legal(tenant_id, role)
    matter = LegalMatter(tenant_id=tenant_id, client_id=str(body.get("client_id", "")), name=str(body.get("name", "")), status="DRAFT", idempotency_key=str(body.get("idempotency_key", uuid4())))
    if not matter.client_id or not matter.name:
        raise HTTPException(422, "client_id and name required")
    db.add(matter)
    await db.commit()
    return {"matter_id": str(matter.id), "status": matter.status}
