import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import settings
from app.core.sales_leads import (
    DisabledProvider,
    FakeOdooReadOnly,
    IdempotencyConflict,
    LeadCandidate,
    OdooRecord,
    SalesLeadService,
    normalize_domain,
    normalize_phone,
    sign_scraper,
    verify_scraper,
)
from app.main import app


def candidate(**changes):
    value = {
        "schema_version": "codestra.sales.lead-candidate.v1",
        "tenant_id": "tenant-a",
        "campaign_id": "campaign-a",
        "source": {
            "provider": "self_hosted_scraper",
            "job_id": "job-1",
            "request_id": "request-1",
            "collected_at": "2026-08-08T12:00:00Z",
        },
        "company": {
            "name": "Acme, Inc.",
            "domain": "https://www.acme.example/path?q=1",
            "website_url": "https://acme.example",
            "country_code": "US",
            "address": {"city": "Miami", "region": "FL", "country_code": "US"},
        },
        "contact": {
            "full_name": "Ada Lovelace",
            "business_email": "ada@acme.example",
            "business_phone": "+13055550123",
            "country_code": "US",
        },
        "evidence": [
            {
                "field": "company.domain",
                "source_url": "https://acme.example/contact",
                "page_title": "Contact",
                "snippet": "Public business evidence",
                "content_hash": "a" * 64,
                "observed_at": "2026-08-08T12:00:00Z",
            }
        ],
        "source_claims": {
            "consent_claimed": True,
            "consent_source": "scraper",
            "consent_timestamp": "2026-08-08T12:00:00Z",
        },
        "metadata": {"batch": 1},
    }
    value.update(changes)
    return value


def model(**changes):
    return LeadCandidate.model_validate(candidate(**changes))


@pytest.mark.parametrize(
    "change",
    [
        {"tenant_id": ""},
        {"campaign_id": ""},
        {"schema_version": "v2"},
        {"unknown": True},
    ],
)
def test_contract_rejects_missing_binding_version_and_unknown_fields(change):
    with pytest.raises(ValidationError):
        model(**change)


def test_valid_minimum_and_full_candidate():
    minimum = candidate(evidence=[], contact={}, source_claims={}, metadata={})
    assert LeadCandidate.model_validate(minimum).tenant_id == "tenant-a"
    assert model().source_claims.consent_claimed is True


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@example.com/a",
        "http://127.0.0.1/a",
        "http://10.0.0.1/a",
        "http://169.254.169.254/a",
        "https://example.com/payload.exe",
        "ftp://example.com/a",
    ],
)
def test_evidence_url_ssrf_and_download_guards(url):
    value = candidate()
    value["evidence"][0]["source_url"] = url
    with pytest.raises(ValidationError):
        LeadCandidate.model_validate(value)


def test_contract_bounds_and_malformed_contact():
    value = candidate()
    value["evidence"] = value["evidence"] * 26
    with pytest.raises(ValidationError):
        LeadCandidate.model_validate(value)
    value = candidate()
    value["evidence"][0]["snippet"] = "x" * 1001
    with pytest.raises(ValidationError):
        LeadCandidate.model_validate(value)
    value = candidate()
    value["contact"]["business_email"] = "not-email"
    with pytest.raises(ValidationError):
        LeadCandidate.model_validate(value)
    value = candidate()
    value["contact"]["business_phone"] = "123"
    with pytest.raises(ValidationError):
        LeadCandidate.model_validate(value)


def test_normalization_is_deterministic_and_conservative():
    assert (
        normalize_domain("https://www.xn--bcher-kva.example/a")
        == "xn--bcher-kva.example"
    )
    assert normalize_domain("https://www.bücher.example/a") == "xn--bcher-kva.example"
    assert normalize_phone("(305) 555-0123 ext 7", "US") == ("+13055550123", "7")
    with pytest.raises(ValueError):
        normalize_phone("3055550123", None)


def test_exact_company_and_contact_resolution():
    record = OdooRecord(
        "tenant-a",
        company_id="company-1",
        lead_id="lead-1",
        domain="acme.example",
        email="ada@acme.example",
        consent="GRANTED",
    )
    result = SalesLeadService(FakeOdooReadOnly([record])).resolve(
        model(), "idempotency-1"
    )
    assert result["decision"] == "EXACT_EXISTING"
    assert result["company_resolution"]["score"] == 95
    assert result["contact_resolution"]["score"] == 100


def test_exact_registration_and_phone_plus_company():
    value = candidate()
    value["company"]["registration_number"] = "REG-1"
    value["company"]["domain"] = None
    value["company"]["website_url"] = None
    value["contact"]["business_email"] = None
    record = OdooRecord(
        "tenant-a",
        company_id="company-1",
        lead_id="lead-1",
        registration_number="REG-1",
        jurisdiction="US",
        phone="+13055550123",
        consent="GRANTED",
    )
    result = SalesLeadService(FakeOdooReadOnly([record])).resolve(
        LeadCandidate.model_validate(value), "idempotency-2"
    )
    assert result["company_resolution"]["score"] == 100
    assert result["contact_resolution"]["score"] == 95


def test_weak_identifiers_create_review_not_merge():
    value = candidate()
    value["company"]["domain"] = None
    value["company"]["website_url"] = None
    value["contact"]["business_email"] = "info@acme.example"
    value["contact"]["business_phone"] = None
    record = OdooRecord(
        "tenant-a",
        company_id="company-1",
        lead_id="lead-1",
        company_name="Acme LLC",
        email="info@acme.example",
        consent="GRANTED",
    )
    service = SalesLeadService(FakeOdooReadOnly([record]))
    result = service.resolve(LeadCandidate.model_validate(value), "idempotency-3")
    assert result["decision"] == "POSSIBLE_DUPLICATE"
    assert result["contact_resolution"]["matched"] is False
    assert len(service.reviews) == 1


def test_shared_switchboard_and_fuzzy_person_do_not_merge():
    record = OdooRecord(
        "tenant-a",
        company_id="other-company",
        lead_id="lead-1",
        phone="+13055550123",
        full_name="Ada Lovelace",
    )
    result = SalesLeadService(FakeOdooReadOnly([record])).resolve(
        model(), "idempotency-4"
    )
    assert result["contact_resolution"]["matched"] is False


def test_cross_tenant_matches_are_denied():
    record = OdooRecord(
        "tenant-b",
        company_id="secret-company",
        lead_id="secret-lead",
        domain="acme.example",
        email="ada@acme.example",
    )
    result = SalesLeadService(FakeOdooReadOnly([record])).resolve(
        model(), "idempotency-5"
    )
    assert result["company_resolution"]["odoo_company_id"] is None
    assert result["contact_resolution"]["odoo_lead_id"] is None


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("global_dnc", "BLOCKED_GLOBAL_DNC"),
        ("campaign_dnc", "BLOCKED_CAMPAIGN_DNC"),
        ("suppressed", "BLOCKED_INTERNAL_SUPPRESSION"),
        ("consent", "BLOCKED_CONSENT_WITHDRAWN"),
    ],
)
def test_compliance_precedence_blocks_high_scores(field, expected):
    args = {field: True} if field != "consent" else {field: "WITHDRAWN"}
    record = OdooRecord(
        "tenant-a",
        company_id="company-1",
        lead_id="lead-1",
        domain="acme.example",
        email="ada@acme.example",
        campaign_id="campaign-a",
        **args,
    )
    result = SalesLeadService(FakeOdooReadOnly([record])).resolve(
        model(), f"block-{field}"
    )
    assert result["decision"] == "BLOCKED"
    assert expected in result["gates"].values()


def test_campaign_dnc_is_campaign_scoped_and_unknown_consent_reviews():
    record = OdooRecord("tenant-a", campaign_id="other", campaign_dnc=True)
    result = SalesLeadService(FakeOdooReadOnly([record])).resolve(
        model(), "campaign-scope"
    )
    assert result["gates"]["campaign_dnc"] == "ELIGIBLE"
    assert result["review_required"] is True


def test_odoo_dependency_failure_fails_closed_and_has_zero_writes():
    odoo = FakeOdooReadOnly(unavailable=True)
    result = SalesLeadService(odoo).resolve(model(), "odoo-down")
    assert result["decision"] == "BLOCKED"
    assert "ODOO_DEPENDENCY_UNAVAILABLE" in result["rejection_reasons"]
    assert (odoo.create_count, odoo.update_count, odoo.delete_count) == (0, 0, 0)


def test_idempotency_replay_conflict_concurrency_and_tenant_scope():
    service = SalesLeadService()
    original = service.resolve(model(), "same-key")
    assert service.resolve(model(), "same-key") == original
    changed = candidate()
    changed["company"]["name"] = "Changed"
    with pytest.raises(IdempotencyConflict):
        service.resolve(LeadCandidate.model_validate(changed), "same-key")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: service.resolve(model(), "concurrent-key"), range(4))
        )
    assert len({item["candidate_id"] for item in results}) == 1
    other = candidate(tenant_id="tenant-b")
    assert (
        service.resolve(LeadCandidate.model_validate(other), "same-key")["candidate_id"]
        != original["candidate_id"]
    )


def test_dry_run_job_is_bounded_idempotent_and_write_protected():
    service = SalesLeadService()
    body = {
        "source": "odoo",
        "tenant_id": "tenant-a",
        "campaign_id": None,
        "filters": {"verification_status": ["UNVERIFIED"]},
        "dry_run": True,
        "write_changes": False,
        "publish_to_vicidial": False,
        "batch_size": 100,
    }
    job = service.create_job(body, "job-key")
    assert service.create_job(body, "job-key").job_id == job.job_id
    assert job.state == "COMPLETED"
    for key in ("dry_run", "write_changes", "publish_to_vicidial"):
        invalid = dict(body)
        invalid[key] = not invalid[key]
        with pytest.raises(ValueError):
            service.create_job(invalid, f"invalid-{key}")
    invalid = dict(body)
    invalid["batch_size"] = 101
    with pytest.raises(ValueError):
        service.create_job(invalid, "invalid-batch")


def test_scraper_ingestion_idempotency_and_payload_conflict():
    service = SalesLeadService()
    original = service.accept_scraper(model(), "scraper-key")
    assert service.accept_scraper(model(), "scraper-key") == original
    changed = candidate()
    changed["company"]["name"] = "Changed"
    with pytest.raises(IdempotencyConflict):
        service.accept_scraper(LeadCandidate.model_validate(changed), "scraper-key")


def scraper_headers(body: bytes, nonce="nonce-12345678", timestamp=None):
    timestamp = timestamp or datetime.now(UTC).isoformat()
    values = {
        "X-Scraper-Identity": "scraper-c",
        "X-Tenant-ID": "tenant-a",
        "X-Campaign-ID": "campaign-a",
        "X-Request-ID": "request-1",
        "X-Codestra-Timestamp": timestamp,
        "X-Codestra-Nonce": nonce,
        "X-Content-SHA256": hashlib.sha256(body).hexdigest(),
        "X-Signature-Version": "HMAC-V1",
    }
    values["X-Codestra-Signature"] = sign_scraper(
        body,
        b"test-secret",
        identity="scraper-c",
        tenant="tenant-a",
        campaign="campaign-a",
        request_id="request-1",
        timestamp=timestamp,
        nonce=nonce,
    )
    return values


def test_scraper_auth_accepts_valid_and_rejects_replay_modified_expired_unknown():
    body = json.dumps(candidate()).encode()
    nonces = set()
    headers = scraper_headers(body)
    verify_scraper(body, headers, b"test-secret", "scraper-c", nonces)
    with pytest.raises(PermissionError, match="REPLAYED_NONCE"):
        verify_scraper(body, headers, b"test-secret", "scraper-c", nonces)
    with pytest.raises(PermissionError, match="MODIFIED_PAYLOAD"):
        verify_scraper(
            body + b" ",
            scraper_headers(body, "nonce-2"),
            b"test-secret",
            "scraper-c",
            set(),
        )
    old = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    with pytest.raises(PermissionError, match="EXPIRED_TIMESTAMP"):
        verify_scraper(
            body,
            scraper_headers(body, "nonce-3", old),
            b"test-secret",
            "scraper-c",
            set(),
        )
    with pytest.raises(PermissionError, match="UNKNOWN_SCRAPER_IDENTITY"):
        verify_scraper(body, headers, b"test-secret", "other", set())


def test_disabled_provider_never_fabricates_or_calls():
    result = DisabledProvider().execute(
        tenant_id="tenant-a", campaign_id="campaign-a", operation="verify", payload={}
    )
    assert result.status == "DEPENDENCY_UNAVAILABLE"
    assert DisabledProvider.usage_count == 0 and DisabledProvider.cost_micro_usd == 0


def test_api_validation_error_is_sanitized_and_resolution_disabled_by_default():
    original_secret = settings.middleware_secret
    settings.middleware_secret = "test-bearer"
    try:
        client = TestClient(app)
        headers = {
            "Authorization": "Bearer test-bearer",
            "content-type": "application/json",
        }
        response = client.post(
            "/api/v1/sales/lead-candidates/validate", content=b"{}", headers=headers
        )
        assert (
            response.status_code == 422
            and response.json()["error"]["code"] == "LEAD_CANDIDATE_INVALID"
        )
        response = client.post(
            "/api/v1/sales/lead-candidates/resolve",
            json=candidate(),
            headers={**headers, "Idempotency-Key": "api-key-1"},
        )
        assert (
            response.status_code == 503
            and response.json()["error"]["code"] == "SALES_FEATURE_DISABLED"
        )
        assert "traceback" not in response.text.lower()
    finally:
        settings.middleware_secret = original_secret


def test_openapi_documents_every_sales_route_and_strict_candidate_body():
    schema = app.openapi()
    expected = {
        "/api/v1/sales/lead-candidates/validate",
        "/api/v1/sales/lead-candidates/resolve",
        "/api/v1/sales/verification-jobs",
        "/api/v1/sales/verification-jobs/{job_id}",
        "/api/v1/sales/verification-jobs/{job_id}/results",
        "/api/v1/sales/scraper-results",
    }
    assert expected <= set(schema["paths"])
    body = schema["paths"]["/api/v1/sales/lead-candidates/resolve"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"]
    assert body["additionalProperties"] is False
    assert body["properties"]["schema_version"]["title"] == "Schema Version"
