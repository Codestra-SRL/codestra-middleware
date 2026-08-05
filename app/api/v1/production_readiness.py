"""Section 12 release evidence and production-readiness API."""

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.production_certification import (
    ProductionCertificationEvidence,
    certify_production,
    disaster_recovery_evidence_valid,
    rollback_evidence_valid,
)

router = APIRouter(prefix="/api/v1/production-readiness", tags=["production-readiness"])
READ_ROLES = frozenset({"RELEASE_MANAGER", "SECURITY_AUDITOR", "OPERATIONS", "EXECUTIVE_READ_ONLY"})


class CertificationRequest(BaseModel):
    release_id: str
    version: str
    environment: str
    strategy: str
    canary_scope: str = ""
    gates: dict[str, bool]
    release_owner: str
    security_owner: str
    rollback_authority: str
    backup_reference: str
    restore_reference: str
    rollback_reference: str
    disaster_recovery_reference: str
    maintenance_window_reference: str
    feature_flags: dict[str, bool]
    production_activation: bool = False


class RollbackEvidenceRequest(BaseModel):
    authorized: bool
    rehearsed: bool
    target_version: str
    verification_reference: str


class DisasterRecoveryRequest(BaseModel):
    backup_verified: bool
    restore_verified: bool
    rpo_seconds: int = Field(ge=0)
    rto_seconds: int = Field(gt=0)
    evidence_reference: str


def _role_guard(role: str) -> None:
    if role not in READ_ROLES:
        raise HTTPException(403, "release governance role required")


@router.get("/overview")
async def overview(role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    _role_guard(role)
    return {
        "section": "12",
        "status": "READY_FOR_CERTIFICATION",
        "release_governance": True,
        "production_activation": False,
        "automatic_deployment": False,
        "automatic_rollback": False,
        "feature_flag_writes": False,
        "strategies": ["STAGING_ONLY", "FEATURE_FLAG", "CANARY", "BLUE_GREEN", "ROLLING", "MAINTENANCE"],
    }


@router.post("/certifications")
async def certify(body: CertificationRequest, role: str = Header("", alias="X-Codestra-Role")) -> dict[str, str]:
    if role != "RELEASE_MANAGER":
        raise HTTPException(403, "release manager approval required")
    valid, reason = certify_production(ProductionCertificationEvidence(**body.model_dump()))
    if not valid:
        raise HTTPException(403, reason)
    return {"status": "CERTIFIED_FOR_CONTROLLED_PLANNING", "production_activation": "DISABLED", "audit": "REQUIRED"}


@router.post("/rollback/validate")
async def validate_rollback(body: RollbackEvidenceRequest, role: str = Header("", alias="X-Codestra-Role")) -> dict[str, str]:
    _role_guard(role)
    if not rollback_evidence_valid(**body.model_dump()):
        raise HTTPException(403, "rollback evidence incomplete")
    return {"status": "PASS", "automatic_rollback": "DISABLED"}


@router.post("/disaster-recovery/validate")
async def validate_disaster_recovery(body: DisasterRecoveryRequest, role: str = Header("", alias="X-Codestra-Role")) -> dict[str, str]:
    _role_guard(role)
    if not disaster_recovery_evidence_valid(**body.model_dump()):
        raise HTTPException(403, "disaster recovery evidence incomplete")
    return {"status": "PASS", "production_failover": "DISABLED"}
