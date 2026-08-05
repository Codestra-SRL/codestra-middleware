"""Read-only Section 11 security and compliance evidence surface."""

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.security_governance import COMPLIANCE_FRAMEWORKS, SECURITY_DOMAINS

router = APIRouter(prefix="/api/v1/security-governance", tags=["security-governance"])
READ_ROLES = frozenset({"SECURITY_ADMIN", "SECURITY_AUDITOR", "COMPLIANCE_AUDITOR", "AI_PLATFORM_ADMIN", "EXECUTIVE_READ_ONLY"})


def _require_role(role: str) -> None:
    if role not in READ_ROLES:
        raise HTTPException(403, "security governance role required")


@router.get("/overview")
async def overview(role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    _require_role(role)
    return {
        "mode": "read_only_evidence",
        "domains": sorted(SECURITY_DOMAINS),
        "frameworks": sorted(COMPLIANCE_FRAMEWORKS),
        "critical_findings": 0,
        "high_findings": 0,
        "audit_complete": False,
        "policies_complete": True,
        "production_actions": False,
        "autonomous_actions": False,
        "evidence_source": "middleware_governance",
    }
