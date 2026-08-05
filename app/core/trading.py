"""Fail-closed paper/demo trading policy contracts."""
from dataclasses import dataclass

ACCOUNT_TYPES = frozenset({"DEMO_FOREX", "DEMO_CRYPTO", "PAPER_FOREX", "PAPER_CRYPTO"})
ORDER_STATES = frozenset({"DRAFT", "VALIDATING", "REJECTED", "ACCEPTED", "PENDING", "PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING", "CANCELLED", "EXPIRED", "FAILED", "UNKNOWN", "RECONCILIATION_REQUIRED"})
ORDER_TYPES = frozenset({"MARKET", "LIMIT", "STOP", "STOP_LIMIT", "TAKE_PROFIT", "STOP_LOSS"})


class TradingPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class OrderValidation:
    account_type: str
    account_active: bool
    instrument_active: bool
    market_state: str
    price_fresh: bool
    quantity: float
    minimum_quantity: float
    maximum_quantity: float
    available_balance: float
    estimated_notional: float
    emergency_stop: bool = False


@dataclass(frozen=True)
class LedgerBalance:
    assets: int
    liabilities: int
    equity: int


def validate_account_type(account_type: str) -> str:
    if account_type not in ACCOUNT_TYPES:
        raise TradingPolicyError("live or unsupported account type is disabled")
    return account_type


def authorize_order(order: OrderValidation) -> bool:
    validate_account_type(order.account_type)
    if order.emergency_stop or not order.account_active or not order.instrument_active:
        return False
    if order.market_state not in {"LIVE", "DELAYED", "SIMULATED"} or not order.price_fresh:
        return False
    if order.quantity < order.minimum_quantity or order.quantity > order.maximum_quantity:
        return False
    return order.estimated_notional >= 0 and order.estimated_notional <= order.available_balance


def ledger_balances(balance: LedgerBalance) -> bool:
    return balance.assets - balance.liabilities == balance.equity
