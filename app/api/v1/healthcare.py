from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.healthcare import validate_service_level, HealthcarePolicyError
from app.db.models import HealthcarePatient, HealthcareFacility, HealthcareTrip
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/healthcare", tags=["healthcare"])


def require_healthcare(tenant_id: str, role: str) -> None:
    if not tenant_id or not role:
        raise HTTPException(403, "healthcare authorization required")
    if not settings.healthcare_platform_enabled:
        raise HTTPException(404, "healthcare platform unavailable")


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_healthcare(tenant_id, role)
    return {"tenant_id": tenant_id, "status": "read_model_pending", "clinical_decisions": False}


@router.post("/patients", status_code=202)
async def create_patient(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_healthcare(tenant_id, role)
    patient = HealthcarePatient(tenant_id=tenant_id, display_name=str(body.get("display_name", "")), preferred_language=str(body.get("preferred_language", "")), data_classification="PROTECTED")
    if not patient.display_name:
        raise HTTPException(422, "display_name required")
    db.add(patient)
    await db.commit()
    return {"patient_id": str(patient.id), "status": "ACTIVE"}


@router.post("/facilities", status_code=202)
async def create_facility(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_healthcare(tenant_id, role)
    facility = HealthcareFacility(tenant_id=tenant_id, name=str(body.get("name", "")), status="ACTIVE")
    if not facility.name:
        raise HTTPException(422, "facility name required")
    db.add(facility)
    await db.commit()
    return {"facility_id": str(facility.id), "status": facility.status}


@router.post("/trips", status_code=202)
async def create_trip(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_healthcare(tenant_id, role)
    try:
        service_level = validate_service_level(str(body.get("service_level", "")))
    except HealthcarePolicyError as exc:
        raise HTTPException(422, str(exc)) from exc
    trip = HealthcareTrip(tenant_id=tenant_id, patient_id=str(body.get("patient_id", "")), pickup_reference=str(body.get("pickup_reference", "")), destination_reference=str(body.get("destination_reference", "")), service_level=service_level, status="DRAFT", idempotency_key=str(body.get("idempotency_key", uuid4())))
    db.add(trip)
    await db.commit()
    return {"trip_id": str(trip.id), "status": trip.status}
