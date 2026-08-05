from typing import Any
from fastapi import APIRouter, Header, HTTPException

from app.core.ai_governance import EvaluationGate, evaluate_gate, GovernanceError, validate_promotion
from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai-governance", tags=["ai-governance"])


def require_governance(role: str) -> None:
    if role not in {"AI_PLATFORM_ADMIN", "AI_SECURITY_ADMIN", "AI_AUDITOR", "AI_REVIEWER"}:
        raise HTTPException(403, "AI governance role required")
    if not settings.ai_governance_enabled:
        raise HTTPException(404, "AI governance unavailable")


@router.post("/evaluate")
async def evaluate(body: dict[str, Any], role: str = Header("", alias="X-Codestra-Role")) -> dict[str, str]:
    require_governance(role)
    gate = EvaluationGate(float(body.get("schema_pass_rate", 0)), int(body.get("unsupported_claims", 0)), int(body.get("critical_compliance_findings", 0)), bool(body.get("human_review_complete", False)))
    return {"outcome": evaluate_gate(gate)}


@router.post("/promote")
async def promote(body: dict[str, Any], role: str = Header("", alias="X-Codestra-Role")) -> dict[str, str]:
    require_governance(role)
    try:
        status = validate_promotion(str(body.get("state", "")), str(body.get("gate_outcome", "")), settings.ai_production_promotion_enabled)
    except GovernanceError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": status}
