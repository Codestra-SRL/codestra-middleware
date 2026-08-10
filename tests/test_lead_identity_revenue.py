from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.config import Settings
from app.leads.domain import (
    MatchConfidence,
    NextAction,
    attribution_weights,
    build_utm,
    match_identity,
    next_best_action,
    normalize_domain,
    normalize_email,
    normalize_phone,
    quality_score,
    stable_hash,
)


def test_email_normalization_is_conservative():
    assert normalize_email(" Sales@Example.COM ") == "sales@example.com"
    with pytest.raises(ValueError, match="LEAD_EMAIL_INVALID"):
        normalize_email("missing-at.example")
    assert (
        normalize_email("first.last+campaign@example.com")
        == "first.last+campaign@example.com"
    )


def test_phone_normalization_does_not_invent_country():
    assert normalize_phone("+1 (202) 555-0123") == ("+12025550123", "NORMALIZED")
    assert normalize_phone("2025550123") == (None, "AMBIGUOUS")
    assert normalize_phone("2025550123", "US") == ("+12025550123", "NORMALIZED")


def test_domain_normalization_supports_idna_without_paths():
    assert normalize_domain("https://www.Example.com/path?q=1") == "example.com"
    assert normalize_domain("https://münich.example/about") == "xn--mnich-kva.example"
    with pytest.raises(ValueError, match="LEAD_DOMAIN_INVALID"):
        normalize_domain("https://user:password@example.com")


def test_exact_identity_matching_and_conflict():
    exact = match_identity({"email": "a@example.com"}, {"email": "a@example.com"})
    assert exact.confidence == MatchConfidence.EXACT and exact.auto_link
    conflict = match_identity(
        {"email": "a@example.com", "phone": "+12025550123"},
        {"email": "b@example.com", "phone": "+12025550123"},
    )
    assert conflict.conflict and not conflict.auto_link


def test_composite_match_is_explainable_and_never_auto_merges():
    result = match_identity(
        {"name": "Ada Lovelace", "company_domain": "example.com", "country": "GB"},
        {"name": "Ada Lovelace", "company_domain": "example.com", "country": "GB"},
    )
    assert result.confidence == MatchConfidence.HIGH
    assert result.score == 80
    assert not result.auto_link
    assert result.signals == {"name": 30, "company_domain": 40, "country": 10}


def test_quality_score_has_visible_bounded_components():
    score, components = quality_score(
        {"intent_quality": 999, "contactability": 10, "urgency": -5}
    )
    assert score == 35
    assert components["intent_quality"] == 25
    assert components["urgency"] == 0


def test_dnc_and_consent_have_final_authority():
    assert (
        next_best_action(
            dnc="INTERNAL_DNC",
            consent="GRANTED",
            intent="BUYING_INTENT",
            score=100,
            phone=True,
            email=True,
            social=True,
        ).action
        == NextAction.DO_NOT_CONTACT
    )
    unknown = next_best_action(
        dnc="CLEAR",
        consent="UNKNOWN",
        intent="BUYING_INTENT",
        score=100,
        phone=True,
        email=True,
        social=True,
    )
    assert unknown.action == NextAction.MANUAL_REVIEW
    assert not unknown.eligible_for_contact


def test_next_action_rules_are_deterministic():
    decision = next_best_action(
        dnc="CLEAR",
        consent="GRANTED",
        intent="BUYING_INTENT",
        score=80,
        phone=True,
        email=True,
        social=True,
    )
    assert decision.action == NextAction.CALL_NOW
    assert decision.reasons == ("HIGH_BUYING_INTENT", "VALID_PHONE")


def test_utm_uses_stable_codestra_identifiers():
    assert (
        build_utm("Facebook", "CMP-123", "CNT-v2")
        == "utm_source=facebook&utm_medium=social&utm_campaign=CMP-123&utm_content=CNT-v2"
    )


def test_all_attribution_models_allocate_exactly_one():
    now = datetime.now(timezone.utc)
    touches = [
        now - timedelta(days=10),
        now - timedelta(days=5),
        now - timedelta(days=1),
    ]
    for model in (
        "FIRST_TOUCH",
        "LAST_TOUCH",
        "LINEAR",
        "POSITION_BASED",
        "TIME_DECAY",
    ):
        weights = attribution_weights(model, touches, now)
        assert sum(weights) == Decimal(1)
        assert len(weights) == 3
    assert attribution_weights("FIRST_TOUCH", touches, now) == [
        Decimal(1),
        Decimal(0),
        Decimal(0),
    ]
    assert attribution_weights("LAST_TOUCH", touches, now) == [
        Decimal(0),
        Decimal(0),
        Decimal(1),
    ]
    assert attribution_weights("POSITION_BASED", touches, now) == [
        Decimal("0.4"),
        Decimal("0.2"),
        Decimal("0.4"),
    ]


def test_revenue_reference_hash_is_deterministic_without_exposure():
    assert stable_hash("ODOO-SALE-1") == stable_hash("ODOO-SALE-1")
    assert "ODOO-SALE-1" not in stable_hash("ODOO-SALE-1")


def test_n7_feature_flags_fail_closed():
    value = Settings()
    assert not value.identity_graph_enabled
    assert not value.lead_intelligence_enabled
    assert not value.next_best_action_enabled
    assert not value.attribution_engine_enabled
    assert not value.revenue_event_sync_enabled
    assert not value.automatic_contacting_enabled
    value.automatic_contacting_enabled = True
    with pytest.raises(ValueError, match="automatic lead contacting is forbidden"):
        value.validate_safety()


def test_openapi_has_provider_neutral_n7_contracts():
    from app.main import app

    paths = app.openapi()["paths"]
    required = {
        "/api/v1/identity/resolve",
        "/api/v1/identity/persons/{person_id}",
        "/api/v1/identity/merge",
        "/api/v1/identity/unmerge",
        "/api/v1/identity/companies/resolve",
        "/api/v1/identity/companies/{company_id}",
        "/api/v1/identity/{identity_id}/timeline",
        "/api/v1/leads",
        "/api/v1/leads/{lead_id}/interactions",
        "/api/v1/leads/{lead_id}/next-action",
        "/api/v1/leads/{lead_id}/action-feedback",
        "/api/v1/analytics/attribution/revenue",
        "/api/v1/analytics/attribution/revenue/{event_id}/calculate",
        "/api/v1/analytics/attribution/touches",
        "/api/v1/analytics/attribution/{dimension}",
        "/api/v1/ops/leads",
        "/api/v1/ops/leads/{lead_id}",
        "/api/v1/ops/identities/{identity_id}",
    }
    assert required <= set(paths)
    schema = str(app.openapi()).casefold()
    assert "oauth_token" not in schema and "provider_secret" not in schema


def test_integration_runtime_exposes_n7_contracts():
    from app.entrypoints.integration_api import app

    paths = app.openapi()["paths"]
    assert "/api/v1/identity/resolve" in paths
    assert "/api/v1/leads/{lead_id}/next-action" in paths
    assert "/api/v1/analytics/attribution/revenue" in paths
