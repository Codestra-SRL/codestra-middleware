"""Fail-closed allocation API backed by the authoritative pool ledger.

This PR exposes extension reservations only. Identity/lead provisioning is
intentionally not faked: those resource families remain unavailable until
their cross-system providers are registered.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.telephony import ReserveRequest, reserve
from app.db.models import TelephonyExtensionReservation
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/allocations", tags=["allocations"])


class ExtensionReservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_public_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    business_unit_public_id: str = Field(min_length=1, max_length=64)
    role_class: str = Field(min_length=1, max_length=32)
    idempotency_key: str = Field(min_length=16, max_length=256)
    evidence_by_extension: dict[int, dict[str, str]] = Field(default_factory=dict)
    ttl_seconds: int = Field(default=900, ge=60, le=3600)


@router.post("/extensions", status_code=201)
async def reserve_extension(
    body: ExtensionReservationRequest,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await reserve(
        ReserveRequest(
            employee_id=body.agent_public_id,
            request_id=body.request_id,
            business_unit=body.business_unit_public_id,
            role_class=body.role_class,
            idempotency_key=body.idempotency_key,
            evidence_by_extension=body.evidence_by_extension,
            ttl_seconds=body.ttl_seconds,
        ),
        db,
    )
    return {"resource_type": "EXTENSION", **result}


@router.get("/{reservation_id}")
async def read_reservation(
    reservation_id: UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    row = await db.get(TelephonyExtensionReservation, reservation_id)
    if row is None:
        raise HTTPException(404, "allocation reservation not found")
    return {"reservation_id": str(row.id), "resource_type": "EXTENSION", "extension": row.extension, "state": row.state, "expires_at": row.expires_at.isoformat()}


@router.post("/{reservation_id}/renew")
async def renew_reservation(
    reservation_id: UUID,
    db: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    row = await db.get(TelephonyExtensionReservation, reservation_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "allocation reservation not found")
    if row.state != "RESERVED" or row.expires_at <= datetime.now(UTC):
        raise HTTPException(409, "reservation is not renewable")
    row.expires_at = datetime.now(UTC) + timedelta(seconds=900)
    await db.commit()
    return {"reservation_id": str(row.id), "state": row.state, "expires_at": row.expires_at.isoformat()}


async def _transition(reservation_id: UUID, state: str, db: AsyncSession) -> dict[str, object]:
    row = await db.get(TelephonyExtensionReservation, reservation_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "allocation reservation not found")
    allowed = {"RESERVED": {"ACTIVE", "RELEASED", "EXPIRED"}, "ACTIVE": {"RELEASED"}}
    if state not in allowed.get(row.state, set()):
        raise HTTPException(409, "invalid allocation transition")
    row.state = state
    if state == "RELEASED":
        row.released_at = datetime.now(UTC)
    if state == "ACTIVE":
        row.activated_at = datetime.now(UTC)
    await db.commit()
    return {"reservation_id": str(row.id), "state": row.state, "extension": row.extension}


@router.post("/{reservation_id}/commit")
async def commit_reservation(reservation_id: UUID, db: Annotated[AsyncSession, Depends(get_session)]):
    return await _transition(reservation_id, "ACTIVE", db)


@router.post("/{reservation_id}/release")
async def release_reservation(reservation_id: UUID, db: Annotated[AsyncSession, Depends(get_session)]):
    return await _transition(reservation_id, "RELEASED", db)


@router.post("/identities", status_code=503)
async def identities_unavailable() -> None:
    raise HTTPException(503, "identity allocation provider is not registered")


@router.post("/test-resources", status_code=503)
async def test_resources_unavailable() -> None:
    raise HTTPException(503, "cross-system test-resource allocator is not registered")
