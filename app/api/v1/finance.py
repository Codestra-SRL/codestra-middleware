from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.finance import FinancePolicyError, validate_application_state
from app.db.models import FinanceApplicant, FinanceApplication
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/finance", tags=["finance"])


def require_finance(tenant_id: str, role: str) -> None:
    if not tenant_id or not role:
        raise HTTPException(403, "financial-services authorization required")
    if not settings.finance_platform_enabled:
        raise HTTPException(404, "financial-services platform unavailable")


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_finance(tenant_id, role)
    return {"tenant_id": tenant_id, "status": "read_model_pending", "automatic_credit_decisions": False}


@router.post("/applicants", status_code=202)
async def create_applicant(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_finance(tenant_id, role)
    applicant = FinanceApplicant(tenant_id=tenant_id, display_name=str(body.get("display_name", "")), applicant_type=str(body.get("applicant_type", "APPLICANT")))
    if not applicant.display_name:
        raise HTTPException(422, "display_name required")
    db.add(applicant)
    await db.commit()
    return {"applicant_id": str(applicant.id), "status": "ACTIVE"}


@router.post("/applications", status_code=202)
async def create_application(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_finance(tenant_id, role)
    try:
        state = validate_application_state(str(body.get("status", "DRAFT")))
    except FinancePolicyError as exc:
        raise HTTPException(422, str(exc)) from exc
    application = FinanceApplication(tenant_id=tenant_id, applicant_id=str(body.get("applicant_id", "")), status=state, idempotency_key=str(body.get("idempotency_key", uuid4())))
    if not application.applicant_id:
        raise HTTPException(422, "applicant_id required")
    db.add(application)
    await db.commit()
    return {"application_id": str(application.id), "status": application.status}
