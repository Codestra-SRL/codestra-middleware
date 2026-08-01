import json
import time

from fastapi.testclient import TestClient

from app.core.automation import sign_exact_body
from app.core.config import settings
from app.main import app


def _event() -> dict:
    now = "2026-08-01T16:00:00Z"
    return {
        "event_id": "evt-preflight-only",
        "event_type": "lead.hot",
        "event_version": "1.0",
        "occurred_at": now,
        "received_at": now,
        "tenant_id": "staging",
        "environment": "staging",
        "request_id": "req-preflight-only",
        "correlation_id": "corr-preflight-only",
        "idempotency_key": "idem-preflight-only",
        "source": "preflight",
        "campaign_id": "TEST_SYN",
        "originating_odoo_outbox_id": "odoo-outbox-preflight-only",
        "originating_middleware_outbox_id": "middleware-outbox-preflight-only",
        "synthetic": True,
        "references": {},
        "data": {},
    }


def _request(event: dict, signature: str) -> dict:
    return {
        "event": event,
        "source_headers": {
            "x-codestra-event-id": event["event_id"],
            "x-codestra-workflow-id": "WF-00",
            "x-codestra-timestamp": str(int(time.time())),
            "x-codestra-signature": signature,
        },
    }


def test_verifier_fails_closed_and_checks_dispatch_signature(monkeypatch):
    monkeypatch.setattr(settings, "n8n_internal_auth_header", "X-Internal-Test")
    monkeypatch.setattr(settings, "n8n_internal_auth_token", "protected-test-token")
    monkeypatch.setattr(settings, "outbox_signature_secret", "signature-test-secret")
    monkeypatch.setattr(settings, "automation_environment", "staging")
    event = _event()
    raw = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()
    body = _request(event, sign_exact_body(raw, settings.outbox_signature_secret))
    client = TestClient(app)

    assert client.post("/api/v1/automation/events/verify", json=body).status_code == 401
    assert client.post(
        "/api/v1/automation/events/verify",
        json=body,
        headers={"X-Internal-Test": "incorrect"},
    ).status_code == 401
    bad_signature = _request(event, "sha256=" + "0" * 64)
    assert client.post(
        "/api/v1/automation/events/verify",
        json=bad_signature,
        headers={"X-Internal-Test": "protected-test-token"},
    ).status_code == 401
    response = client.post(
        "/api/v1/automation/events/verify",
        json=body,
        headers={"X-Internal-Test": "protected-test-token"},
    )
    assert response.status_code == 200
    assert response.json()["verified"] is True
    assert response.json()["correlation_id"] == event["correlation_id"]


def test_callback_routes_require_internal_auth(monkeypatch):
    monkeypatch.setattr(settings, "n8n_internal_auth_header", "X-Internal-Test")
    monkeypatch.setattr(settings, "n8n_internal_auth_token", "protected-test-token")
    client = TestClient(app)
    assert client.post("/api/v1/n8n/executions", json={}).status_code == 401
    assert client.post("/api/v1/n8n/acknowledgements", json={}).status_code == 401
    assert client.post("/api/v1/n8n/results", json={}).status_code == 401
    assert client.post("/api/v1/n8n/internal-results", json={}).status_code == 401
    assert client.post("/api/v1/n8n/failures", json={}).status_code == 401
