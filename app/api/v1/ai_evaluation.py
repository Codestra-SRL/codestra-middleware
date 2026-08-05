from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.ai_evaluation import PromotionRequest, authorize_promotion
from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai-workforce", tags=["ai-evaluation"])


@router.get("/evaluations")
async def evaluations(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.ai_evaluation_platform_enabled:
        raise HTTPException(404, "Evaluation platform unavailable")
    if not tenant_id:
        raise HTTPException(403, "Tenant scope required")
    return {"tenant_id": tenant_id, "runs": [], "production_promotion": False}


@router.post("/learning/proposals/{proposal_id}/promote-staging")
async def promote_staging(proposal_id: str, request: PromotionRequest) -> dict[str, Any]:
    if not settings.ai_staging_promotion_enabled:
        raise HTTPException(404, "Staging promotion unavailable")
    valid, reason = authorize_promotion(request)
    if not valid:
        raise HTTPException(403, reason)
    return {"proposal_id": proposal_id, "state": "STAGING", "production_promotion": False}
