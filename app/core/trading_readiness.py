"""Fail-closed trading sandbox, compliance, and readiness contracts."""
from dataclasses import dataclass

RECONCILIATION_OUTCOMES = frozenset({"MATCHED", "TEMPORARY_DIFFERENCE", "MISSING_INTERNAL", "MISSING_PROVIDER", "AMOUNT_DIFFERENCE", "STATUS_DIFFERENCE", "DUPLICATE", "UNKNOWN", "REVIEW_REQUIRED"})
JURISDICTION_OUTCOMES = frozenset({"ALLOWED_DEMO", "ALLOWED_PAPER", "LIVE_REVIEW_REQUIRED", "RESTRICTED", "PROHIBITED", "UNKNOWN"})


@dataclass(frozen=True)
class ProviderCallback:
    tenant_id: str
    signature_valid: bool
    replayed: bool
    idempotency_key: str


@dataclass(frozen=True)
class JurisdictionDecision:
    country: str
    product: str
    outcome: str
    verified: bool


@dataclass(frozen=True)
class MarketDataCertification:
    symbol: str
    timestamp_valid: bool
    source_known: bool
    precision_valid: bool
    contract_valid: bool


def accept_provider_callback(callback: ProviderCallback) -> bool:
    return bool(callback.tenant_id and callback.signature_valid and not callback.replayed and callback.idempotency_key)


def allow_demo_or_paper(decision: JurisdictionDecision) -> bool:
    return bool(decision.country and decision.product and decision.verified and decision.outcome in {"ALLOWED_DEMO", "ALLOWED_PAPER"})


def certify_market_data(certification: MarketDataCertification) -> bool:
    return bool(certification.symbol and certification.timestamp_valid and certification.source_known and certification.precision_valid and certification.contract_valid)


def valid_reconciliation_outcome(outcome: str) -> bool:
    return outcome in RECONCILIATION_OUTCOMES
