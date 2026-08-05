import pytest

from app.core.trading import (
    LedgerBalance,
    OrderValidation,
    TradingPolicyError,
    authorize_order,
    ledger_balances,
    validate_account_type,
)


def test_only_demo_and_paper_accounts_are_enabled():
    assert validate_account_type("DEMO_FOREX") == "DEMO_FOREX"
    assert validate_account_type("PAPER_CRYPTO") == "PAPER_CRYPTO"
    with pytest.raises(TradingPolicyError):
        validate_account_type("LIVE_CRYPTO_PENDING_APPROVAL")


def test_order_rejects_stale_or_unsafe_market_data():
    order = OrderValidation("PAPER_FOREX", True, True, "SIMULATED", True, 1, 1, 10, 1000, 100)
    assert authorize_order(order) is True
    assert authorize_order(order.__class__("PAPER_FOREX", True, True, "STALE", True, 1, 1, 10, 1000, 100)) is False


def test_emergency_stop_blocks_without_mutating_balance():
    order = OrderValidation("DEMO_CRYPTO", True, True, "SIMULATED", True, 1, 1, 10, 1000, 100, True)
    assert authorize_order(order) is False


def test_ledger_balance_invariant_is_explicit():
    assert ledger_balances(LedgerBalance(1100, 100, 1000)) is True
    assert ledger_balances(LedgerBalance(1100, 100, 999)) is False

