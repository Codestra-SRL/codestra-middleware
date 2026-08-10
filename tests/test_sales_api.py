from __future__ import annotations

import hashlib
import json
import time

from fastapi.testclient import TestClient

from app.api.v1 import sales
from app.core.config import settings
from app.main import app
from app.sales.auth import NonceLedger, ScraperIdentity, signature
from app.sales.compliance import ComplianceSnapshot
from app.sales.odoo import FakeOdooReadOnlyAdapter, OdooLookup
from app.sales.service import SalesLeadService
from tests.test_sales_lead_foundation import candidate


client = TestClient(app)


def configure(monkeypatch):
    monkeypatch.setattr(settings, "middleware_secret", "test-bearer")
    monkeypatch.setattr(settings, "sales_lead_intake_enabled", True)
    monkeypatch.setattr(settings, "sales_identity_resolution_enabled", True)
    monkeypatch.setattr(settings, "sales_verification_jobs_enabled", True)
    monkeypatch.setattr(settings, "scraper_result_ingest_enabled", True)
    sales.service = SalesLeadService(
        FakeOdooReadOnlyAdapter(
            OdooLookup(
                compliance=ComplianceSnapshot(
                    "tenant-a", "campaign-a", consent="GRANTED", channel_eligible=True
                )
            ),
            [candidate()],
        )
    )
    sales.repository = None
    sales.scraper_nonces = NonceLedger()


def auth():
    return {
        "Authorization": "Bearer test-bearer",
        "Idempotency-Key": "idempotency-key-0001",  # gitleaks:allow test fixture
    }


def test_validate_resolve_openapi_and_sanitized_errors(monkeypatch):
    configure(monkeypatch)
    payload = candidate().model_dump(mode="json")
    assert (
        client.post(
            "/api/v1/sales/lead-candidates/validate", json=payload, headers=auth()
        ).status_code
        == 200
    )
    first = client.post(
        "/api/v1/sales/lead-candidates/resolve", json=payload, headers=auth()
    )
    replay = client.post(
        "/api/v1/sales/lead-candidates/resolve", json=payload, headers=auth()
    )
    assert first.status_code == replay.status_code == 200
    assert replay.headers["x-idempotent-replay"] == "true"
    payload["company"]["name"] = "Changed"
    conflict = client.post(
        "/api/v1/sales/lead-candidates/resolve", json=payload, headers=auth()
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_PAYLOAD_CONFLICT"
    assert "sql" not in conflict.text.lower() and "/root/" not in conflict.text
    paths = app.openapi()["paths"]
    assert "/api/v1/sales/lead-candidates/resolve" in paths
    assert "/api/v1/sales/verification-jobs" in paths


def test_request_size_unknown_field_and_content_type(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(settings, "sales_lead_request_max_bytes", 32)
    response = client.post(
        "/api/v1/sales/lead-candidates/validate",
        content=b"x" * 33,
        headers={**auth(), "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    monkeypatch.setattr(settings, "sales_lead_request_max_bytes", 131072)
    payload = candidate().model_dump(mode="json")
    payload["unknown"] = True
    assert (
        client.post(
            "/api/v1/sales/lead-candidates/validate", json=payload, headers=auth()
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/sales/lead-candidates/validate",
            content=b"{}",
            headers={**auth(), "Content-Type": "text/plain"},
        ).status_code
        == 415
    )


def test_dry_run_job_and_cross_tenant_read_denial(monkeypatch):
    configure(monkeypatch)
    request = {
        "source": "odoo",
        "tenant_id": "tenant-a",
        "campaign_id": "campaign-a",
        "filters": {"verification_status": ["UNVERIFIED"]},
        "dry_run": True,
        "write_changes": False,
        "publish_to_vicidial": False,
        "batch_size": 100,
    }
    created = client.post(
        "/api/v1/sales/verification-jobs", json=request, headers=auth()
    )
    assert created.status_code == 202 and created.json()["state"] == "COMPLETED"
    job_id = created.json()["job_id"]
    assert (
        client.get(
            f"/api/v1/sales/verification-jobs/{job_id}",
            headers={
                "Authorization": "Bearer test-bearer",
                "X-Codestra-Tenant-ID": "tenant-b",
            },
        ).status_code
        == 404
    )
    accepted = client.get(
        f"/api/v1/sales/verification-jobs/{job_id}/results",
        headers={
            "Authorization": "Bearer test-bearer",
            "X-Codestra-Tenant-ID": "tenant-a",
        },
    )
    assert accepted.status_code == 200 and accepted.json()["progress"]["processed"] == 1


def test_valid_invalid_and_replayed_scraper_webhook(monkeypatch, tmp_path):
    configure(monkeypatch)
    secret_file = tmp_path / "scraper-hmac"
    secret_file.write_bytes(b"z" * 32)
    secret_file.chmod(0o600)
    # The production property requires a protected absolute file; API auth semantics
    # are exercised by substituting the already-loaded protected value.
    monkeypatch.setattr(
        type(settings), "sales_scraper_hmac_secret", property(lambda _: b"z" * 32)
    )
    monkeypatch.setattr(settings, "sales_scraper_identity", "scraper-c")
    monkeypatch.setattr(settings, "sales_scraper_tenant_id", "tenant-a")
    monkeypatch.setattr(settings, "sales_scraper_campaign_allowlist", "campaign-a")
    raw = json.dumps(
        candidate().model_dump(mode="json"), separators=(",", ":")
    ).encode()
    timestamp = str(int(time.time()))
    identity = ScraperIdentity(
        "scraper-c", "tenant-a", frozenset({"campaign-a"}), b"z" * 32
    )
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": "scraper-idempotency-0001",
        "X-Codestra-Scraper-ID": "scraper-c",
        "X-Codestra-Timestamp": timestamp,
        "X-Codestra-Nonce": "nonce-api-1",
        "X-Codestra-Signature-Version": "hmac-sha256-v1",
        "X-Codestra-Content-SHA256": hashlib.sha256(raw).hexdigest(),
        "X-Codestra-Signature": signature(
            identity=identity,
            tenant_id="tenant-a",
            campaign_id="campaign-a",
            request_id="request-1",
            timestamp=timestamp,
            nonce="nonce-api-1",
            body=raw,
        ),
    }
    accepted = client.post(
        "/api/v1/sales/scraper-results", content=raw, headers=headers
    )
    assert accepted.status_code == 200
    replay = client.post("/api/v1/sales/scraper-results", content=raw, headers=headers)
    assert replay.status_code == 401 and replay.json()["code"] == "REPLAYED_NONCE"
    invalid = client.post(
        "/api/v1/sales/scraper-results",
        content=raw,
        headers={
            **headers,
            "X-Codestra-Nonce": "nonce-api-2",
            "X-Codestra-Signature": "0" * 64,
        },
    )
    assert invalid.status_code == 401


def test_all_phase_one_flags_default_false():
    configured = type(settings)()
    for name in (
        "sales_lead_intake_enabled",
        "sales_identity_resolution_enabled",
        "sales_odoo_read_only_lookup_enabled",
        "sales_verification_jobs_enabled",
        "scraper_result_ingest_enabled",
        "hunter_provider_enabled",
        "apollo_provider_enabled",
        "twilio_lookup_provider_enabled",
        "opencorporates_provider_enabled",
        "openai_lead_classification_enabled",
        "odoo_write_enabled",
        "vicidial_publication_enabled",
        "outreach_enabled",
    ):
        assert getattr(configured, name) is False
