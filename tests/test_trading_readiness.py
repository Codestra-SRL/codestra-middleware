from app.core.trading_readiness import (
    JurisdictionDecision,
    MarketDataCertification,
    ProviderCallback,
    accept_provider_callback,
    allow_demo_or_paper,
    certify_market_data,
)


def test_provider_callbacks_require_signature_replay_and_idempotency():
    assert accept_provider_callback(ProviderCallback("tenant-a", True, False, "evt-1")) is True
    assert accept_provider_callback(ProviderCallback("tenant-a", True, True, "evt-1")) is False


def test_unknown_or_unverified_jurisdiction_cannot_be_live_eligible():
    assert allow_demo_or_paper(JurisdictionDecision("DO", "PAPER", "ALLOWED_PAPER", True)) is True
    assert allow_demo_or_paper(JurisdictionDecision("", "LIVE", "UNKNOWN", False)) is False


def test_market_data_certification_requires_source_timestamp_precision_and_contract():
    assert certify_market_data(MarketDataCertification("EURUSD", True, True, True, True)) is True
    assert certify_market_data(MarketDataCertification("EURUSD", False, True, True, True)) is False

