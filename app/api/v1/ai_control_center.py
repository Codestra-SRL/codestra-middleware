"""Safe, permission-gated Control Center read models."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai-control-center", tags=["ai-control-center"])


def _guard(role: str, permission: str) -> None:
    if not settings.ai_control_center_enabled:
        raise HTTPException(409, "AI Control Center is disabled")
    if role not in {"AI_PLATFORM_ADMIN", "AI_AUDITOR", "AI_READ_ONLY", "AI_SECURITY_ADMIN", "AI_MODEL_MANAGER", "AI_PROMPT_MANAGER", "LEAD_INTELLIGENCE_MANAGER", "CALL_INTELLIGENCE_VIEWER"}:
        raise HTTPException(403, f"permission required: {permission}")


@router.get("/navigation")
async def navigation(role: str = Header(alias="X-Codestra-Role")) -> dict[str, Any]:
    _guard(role, "ai.overview.read")
    return {"items": [
        {"label": "Overview", "path": "/ai/overview", "permission": "ai.overview.read"},
        {"label": "AI Jobs", "path": "/ai/jobs", "permission": "ai.jobs.read"},
        {"label": "Lead Intelligence", "path": "/ai/leads", "permission": "lead.review.read"},
        {"label": "Call Intelligence", "path": "/ai/calls", "permission": "call.read"},
        {"label": "Agent Assist", "path": "/ai/agent-assist", "permission": "agent_assist.read"},
        {"label": "Knowledge", "path": "/ai/knowledge", "permission": "knowledge.manage"},
        {"label": "Approvals", "path": "/ai/approvals", "permission": "approval.read"},
        {"label": "Models", "path": "/ai/models", "permission": "model.manage"},
        {"label": "Prompts", "path": "/ai/prompts", "permission": "prompt.manage"},
        {"label": "Workflows", "path": "/ai/workflows", "permission": "workflow.manage"},
        {"label": "Integrations", "path": "/ai/integrations", "permission": "integration.read"},
        {"label": "Reconciliation", "path": "/ai/reconciliation", "permission": "audit.read"},
        {"label": "Usage", "path": "/ai/usage", "permission": "usage.read"},
        {"label": "Security", "path": "/ai/security", "permission": "security.read"},
        {"label": "Audit Logs", "path": "/ai/audit", "permission": "audit.read"},
        {"label": "System Health", "path": "/ai/health", "permission": "health.read"},
        {"label": "Settings", "path": "/ai/settings", "permission": "ai.overview.read"},
    ]}


@router.get("/overview")
async def overview(role: str = Header(alias="X-Codestra-Role")) -> dict[str, Any]:
    _guard(role, "ai.overview.read")
    return {"environment": settings.environment, "write_controls": {"production_actions": settings.ai_control_center_production_actions_enabled, "feature_flag_writes": settings.ai_control_center_feature_flag_writes_enabled}, "cards": {"jobs_today": 0, "jobs_running": 0, "jobs_failed": 0, "approvals_pending": 0, "leads_awaiting_review": 0, "calls_analyzed": 0, "compliance_alerts_open": 0}, "data_freshness": "not_connected"}


@router.get("/health")
async def health(role: str = Header(alias="X-Codestra-Role")) -> dict[str, Any]:
    _guard(role, "health.read")
    return {"components": [{"name": name, "status": "UNKNOWN", "safe": True} for name in ("middleware", "odoo", "n8n", "qwen", "faster-whisper", "qdrant", "vicidial", "scraper", "postiz")]}


@router.get("/usage")
async def usage(role: str = Header(alias="X-Codestra-Role")) -> dict[str, Any]:
    _guard(role, "usage.read")
    return {"period": "current", "metrics": [], "data_freshness": "not_connected"}


@router.get("/integrations")
async def integrations(role: str = Header(alias="X-Codestra-Role")) -> dict[str, Any]:
    _guard(role, "integration.read")
    return {"items": [], "data_freshness": "not_connected"}


@router.get("/feature-flags")
async def feature_flags(role: str = Header(alias="X-Codestra-Role")) -> dict[str, Any]:
    _guard(role, "feature_flag.read")
    return {"items": [{"name": "AI_CONTROL_CENTER_PRODUCTION_ACTIONS_ENABLED", "value": settings.ai_control_center_production_actions_enabled, "writable": False}, {"name": "AI_CONTROL_CENTER_FEATURE_FLAG_WRITES_ENABLED", "value": settings.ai_control_center_feature_flag_writes_enabled, "writable": False}]}


@router.get("/security-events")
async def security_events(role: str = Header(alias="X-Codestra-Role")) -> dict[str, Any]:
    _guard(role, "security.read")
    return {"items": [], "count": 0}


@router.get("/reconciliation")
async def reconciliation(role: str = Header(alias="X-Codestra-Role")) -> dict[str, Any]:
    _guard(role, "audit.read")
    return {"items": [], "count": 0}
