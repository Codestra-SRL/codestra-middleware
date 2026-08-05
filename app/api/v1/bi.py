from typing import Any
from fastapi import APIRouter, Header, HTTPException

from app.core.bi import KPI_CONTRACTS
from app.core.config import settings

router = APIRouter(prefix="/api/v1/bi", tags=["executive-bi"])


def require_bi(role: str) -> None:
    if role not in {"AI_PLATFORM_ADMIN", "AI_AUDITOR", "EXECUTIVE", "MANAGER", "CUSTOMER_ANALYST"}:
        raise HTTPException(403, "BI access required")
    if not settings.bi_platform_enabled:
        raise HTTPException(404, "BI platform unavailable")


@router.get("/kpis")
async def kpis(role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_bi(role)
    return {"items": [contract.__dict__ for contract in KPI_CONTRACTS], "source_status": "read_model_pending"}


@router.get("/overview")
async def overview(role: str = Header("", alias="X-Codestra-Role"), tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    require_bi(role)
    if not tenant_id and role == "CUSTOMER_ANALYST":
        raise HTTPException(403, "tenant scope required")
    return {"tenant_id": tenant_id or None, "dashboard": "executive", "freshness": "not_connected", "cards": {contract.code: None for contract in KPI_CONTRACTS}, "forecasting": {"enabled": settings.bi_forecasting_enabled, "status": "advisory_only"}}


@router.get("/dashboards/{dashboard_code}")
async def dashboard(dashboard_code: str, role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_bi(role)
    allowed = {"ceo", "operations", "sales", "call-center", "marketing", "customer-success", "finance"}
    if dashboard_code not in allowed:
        raise HTTPException(404, "dashboard not found")
    return {"dashboard": dashboard_code, "status": "read_model_pending", "kpis": [contract.code for contract in KPI_CONTRACTS]}
