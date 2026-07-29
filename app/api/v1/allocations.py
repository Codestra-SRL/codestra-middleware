"""Fail-closed, durable allocation APIs.

Reservations are authoritative in middleware PostgreSQL.  They do not create
or modify resources in Odoo, Keycloak, VICIdial, Asterisk, Redis, or n8n.
External provisioning belongs to a separately audited saga.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.telephony import ReserveRequest, reserve
from app.db.models import (
    IntegrationAllocationReservation,
    TelephonyExtensionReservation,
)
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


ResourceType = Literal[
    "AGENT_PUBLIC_ID",
    "LEAD_PUBLIC_ID",
    "PHONE_PUBLIC_ID",
    "ENDPOINT_PUBLIC_ID",
    "INTERNAL_TEST_DESTINATION",
]


class IdentityReservationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: Literal["AGENT_PUBLIC_ID", "LEAD_PUBLIC_ID"]
    candidate_public_ids: list[str] = Field(min_length=1, max_length=100)
    environment: str = Field(min_length=1, max_length=24)
    organization_public_id: str = Field(min_length=1, max_length=128)
    business_unit_public_id: str = Field(min_length=1, max_length=128)
    campaign_public_id: str | None = Field(default=None, max_length=128)
    purpose: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=16, max_length=256)
    provider_checks: dict[str, bool] = Field(default_factory=dict)
    ttl_seconds: int = Field(default=900, ge=60, le=3600)


class AllocationBundleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment: str = Field(min_length=1, max_length=24)
    organization_public_id: str = Field(min_length=1, max_length=128)
    business_unit_public_id: str = Field(min_length=1, max_length=128)
    campaign_public_id: str | None = Field(default=None, max_length=128)
    purpose: str = Field(min_length=1, max_length=128)
    identity_reservations: list[IdentityReservationRequest] = Field(
        default_factory=list, max_length=10
    )
    idempotency_key: str = Field(min_length=16, max_length=256)
    provider_checks: dict[str, bool] = Field(default_factory=dict)
    ttl_seconds: int = Field(default=900, ge=60, le=3600)


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _require_provider_checks(checks: dict[str, bool], required: set[str]) -> None:
    missing = sorted(name for name in required if checks.get(name) is not True)
    if missing:
        raise HTTPException(
            503, {"code": "ALLOCATION_PROVIDER_EVIDENCE_REQUIRED", "providers": missing}
        )


async def _reserve_identity(
    body: IdentityReservationRequest, db: AsyncSession
) -> dict[str, object]:
    _require_provider_checks(body.provider_checks, {"middleware", "odoo"})
    if len(set(body.candidate_public_ids)) != len(body.candidate_public_ids):
        raise HTTPException(422, "candidate identities must be unique")
    idem_hash = _hash({"scope": "allocation", "key": body.idempotency_key})
    existing = (
        await db.execute(
            select(IntegrationAllocationReservation).where(
                IntegrationAllocationReservation.idempotency_hash == idem_hash
            )
        )
    ).scalar_one_or_none()
    if existing:
        return {
            "reservation_id": str(existing.id),
            "resource_type": existing.resource_type,
            "resource_public_id": existing.resource_public_id,
            "state": existing.state,
            "idempotency_status": "DUPLICATE",
            "expires_at": existing.expires_at.isoformat(),
        }
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": f"allocation:{body.environment}:{body.resource_type}"},
    )
    active = (
        (
            await db.execute(
                select(IntegrationAllocationReservation.resource_public_id).where(
                    IntegrationAllocationReservation.resource_type
                    == body.resource_type,
                    IntegrationAllocationReservation.resource_public_id.in_(
                        body.candidate_public_ids
                    ),
                    IntegrationAllocationReservation.state.in_(
                        ["RESERVED", "COMMITTED"]
                    ),
                    IntegrationAllocationReservation.expires_at > datetime.now(UTC),
                )
            )
        )
        .scalars()
        .all()
    )
    candidate = next(
        (item for item in body.candidate_public_ids if item not in set(active)), None
    )
    if candidate is None:
        raise HTTPException(409, "no unreserved candidate is available")
    row = IntegrationAllocationReservation(
        resource_type=body.resource_type,
        resource_public_id=candidate,
        environment=body.environment,
        organization_public_id=body.organization_public_id,
        business_unit_public_id=body.business_unit_public_id,
        campaign_public_id=body.campaign_public_id,
        purpose=body.purpose,
        idempotency_hash=idem_hash,
        provider_checks=body.provider_checks,
        expires_at=datetime.now(UTC) + timedelta(seconds=body.ttl_seconds),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "resource reservation conflict") from None
    return {
        "reservation_id": str(row.id),
        "resource_type": row.resource_type,
        "resource_public_id": row.resource_public_id,
        "state": row.state,
        "idempotency_status": "NEW",
        "expires_at": row.expires_at.isoformat(),
        "external_provisioning": "NOT_STARTED",
    }


@router.post("/identities", status_code=201)
async def reserve_identity(
    body: IdentityReservationRequest, db: Annotated[AsyncSession, Depends(get_session)]
):
    return await _reserve_identity(body, db)


@router.post("/test-resources", status_code=201)
async def reserve_test_resources(
    body: AllocationBundleRequest, db: Annotated[AsyncSession, Depends(get_session)]
):
    if not body.identity_reservations:
        raise HTTPException(
            422, "at least one dynamic identity candidate set is required"
        )
    _require_provider_checks(
        body.provider_checks,
        {"middleware", "odoo", "redis", "keycloak", "vicidial", "asterisk", "n8n"},
    )
    results = []
    for item in body.identity_reservations:
        if (
            item.environment != body.environment
            or item.business_unit_public_id != body.business_unit_public_id
        ):
            raise HTTPException(
                422, "nested allocation scope does not match bundle scope"
            )
        results.append(await _reserve_identity(item, db))
    return {
        "state": "RESERVED",
        "idempotency_status": "NEW",
        "reservations": results,
        "external_provisioning": "NOT_STARTED",
    }


@router.post("/extensions", status_code=201)
async def reserve_extension(
    body: ExtensionReservationRequest, db: Annotated[AsyncSession, Depends(get_session)]
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
    reservation_id: UUID, db: Annotated[AsyncSession, Depends(get_session)]
):
    row = await db.get(IntegrationAllocationReservation, reservation_id)
    if row:
        return {
            "reservation_id": str(row.id),
            "resource_type": row.resource_type,
            "resource_public_id": row.resource_public_id,
            "state": row.state,
            "generation": row.generation,
            "expires_at": row.expires_at.isoformat(),
        }
    row_telephony = await db.get(TelephonyExtensionReservation, reservation_id)
    if row_telephony is None:
        raise HTTPException(404, "allocation reservation not found")
    return {
        "reservation_id": str(row_telephony.id),
        "resource_type": "EXTENSION",
        "extension": row_telephony.extension,
        "state": row_telephony.state,
        "expires_at": row_telephony.expires_at.isoformat(),
    }


@router.post("/{reservation_id}/renew")
async def renew_reservation(
    reservation_id: UUID, db: Annotated[AsyncSession, Depends(get_session)]
):
    row = await db.get(
        IntegrationAllocationReservation, reservation_id, with_for_update=True
    )
    if row is None:
        raise HTTPException(404, "allocation reservation not found")
    if row.state != "RESERVED" or row.expires_at <= datetime.now(UTC):
        raise HTTPException(409, "reservation is not renewable")
    row.generation += 1
    row.expires_at = datetime.now(UTC) + timedelta(seconds=900)
    await db.commit()
    return {
        "reservation_id": str(row.id),
        "state": row.state,
        "generation": row.generation,
        "expires_at": row.expires_at.isoformat(),
    }


async def _transition(
    reservation_id: UUID, state: str, db: AsyncSession
) -> dict[str, object]:
    row = await db.get(
        IntegrationAllocationReservation, reservation_id, with_for_update=True
    )
    if row is not None:
        allowed = {
            "RESERVED": {"COMMITTED", "RELEASED", "EXPIRED"},
            "COMMITTED": {"RELEASED"},
        }
        if state not in allowed.get(row.state, set()):
            raise HTTPException(409, "invalid allocation transition")
        row.state = state
        row.generation += 1
        if state == "COMMITTED":
            row.committed_at = datetime.now(UTC)
        if state == "RELEASED":
            row.released_at = datetime.now(UTC)
        await db.commit()
        return {
            "reservation_id": str(row.id),
            "state": row.state,
            "resource_public_id": row.resource_public_id,
        }
    raise HTTPException(404, "allocation reservation not found")


@router.post("/{reservation_id}/commit")
async def commit_reservation(
    reservation_id: UUID, db: Annotated[AsyncSession, Depends(get_session)]
):
    return await _transition(reservation_id, "COMMITTED", db)


@router.post("/{reservation_id}/release")
async def release_reservation(
    reservation_id: UUID, db: Annotated[AsyncSession, Depends(get_session)]
):
    return await _transition(reservation_id, "RELEASED", db)
