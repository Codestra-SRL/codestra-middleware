from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.ai_memory_knowledge import RetrievalContext, authorize_retrieval
from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai-workforce", tags=["ai-memory-knowledge"])


@router.post("/retrieval")
async def retrieval(
    tenant_id: str = Header("", alias="X-Tenant-ID"),
    workspace_id: str = Header("", alias="X-Workspace-ID"),
    employee_id: str = Header("", alias="X-AI-Employee-ID"),
    requested_scope: str = Header("", alias="X-Memory-Scope"),
) -> dict[str, Any]:
    if not settings.ai_memory_platform_enabled or not settings.ai_knowledge_platform_enabled:
        raise HTTPException(404, "Memory and knowledge platform unavailable")
    context = RetrievalContext(tenant_id, workspace_id, employee_id, frozenset(), requested_scope)
    if not authorize_retrieval(context):
        raise HTTPException(403, "Authorized retrieval context required")
    return {"answer_context": [], "citations": [], "excluded_result_count": 0, "authorization_decision": "ALLOWED", "source_freshness": "CURRENT", "confidence": 0.0}
