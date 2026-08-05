from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.trading import TradingPolicyError, validate_account_type
from app.db.models import TradingAccount, TradingInstrument
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/trading", tags=["trading"])


def require_trading(tenant_id: str, role: str) -> None:
    if not tenant_id or not role:
        raise HTTPException(403, "trading authorization required")
    if not settings.trading_platform_enabled:
        raise HTTPException(404, "trading platform unavailable")


@router.get("/overview")
async def overview(tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role")) -> dict[str, Any]:
    require_trading(tenant_id, role)
    return {"tenant_id": tenant_id, "status": "read_model_pending", "real_money": False, "ai_order_execution": False}


@router.post("/accounts", status_code=202)
async def create_account(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_trading(tenant_id, role)
    try:
        account_type = validate_account_type(str(body.get("account_type", "")))
    except TradingPolicyError as exc:
        raise HTTPException(422, str(exc)) from exc
    account = TradingAccount(tenant_id=tenant_id, customer_id=str(body.get("customer_id", "")), account_type=account_type, base_currency=str(body.get("base_currency", "USD")), status="ACTIVE", idempotency_key=str(body.get("idempotency_key", uuid4())))
    if not account.customer_id:
        raise HTTPException(422, "customer_id required")
    db.add(account)
    await db.commit()
    return {"account_id": str(account.id), "account_type": account.account_type, "status": account.status}


@router.post("/instruments", status_code=202)
async def create_instrument(body: dict[str, Any], tenant_id: str = Header("", alias="X-Tenant-ID"), role: str = Header("", alias="X-Codestra-Role"), db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    require_trading(tenant_id, role)
    instrument = TradingInstrument(tenant_id=tenant_id, symbol=str(body.get("symbol", "")), asset_class=str(body.get("asset_class", "")), status="ACTIVE")
    if not instrument.symbol or instrument.asset_class not in {"FOREX", "CRYPTO"}:
        raise HTTPException(422, "symbol and supported asset_class required")
    db.add(instrument)
    await db.commit()
    return {"instrument_id": str(instrument.id), "status": instrument.status}
