from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def _headers(**extra: str) -> dict[str, str]:
    return {
        "Authorization": "Bearer social-api-test",
        "X-Organization-ID": "ORG-API-TEST",
        "X-Workspace-ID": "WS-API-TEST",
        "X-Correlation-ID": "COR-API-TEST",
        **extra,
    }


def _job(job_id: str) -> dict[str, object]:
    return {
        "organization_id": "ORG-API-TEST",
        "workspace_id": "WS-API-TEST",
        "campaign_id": "CMP-API-TEST",
        "content_job_id": job_id,
        "content_version": 1,
        "integration_ids": ["INT-API-TEST"],
        "scheduled_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "preferred_language": "en",
        "correlation_id": "COR-API-TEST",
    }


def _configure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "middleware_secret", "social-api-test")
    monkeypatch.setattr(settings, "social_control_plane_enabled", False)
    monkeypatch.setattr(settings, "social_mock_adapter_enabled", True)
    monkeypatch.setattr(settings, "postly_adapter_enabled", False)


def test_social_route_contract_and_json_lifecycle(monkeypatch):
    _configure(monkeypatch)
    job_id = f"JOB-{uuid4()}"
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/social/jobs", json=_job(job_id), headers=_headers()
        )
        assert created.status_code == 202
        assert created.headers["content-type"].startswith("application/json")
        assert created.headers["x-correlation-id"] == "COR-API-TEST"

        proposal = client.post(
            f"/api/v1/social/jobs/{job_id}/n8n-result",
            json={
                "content_job_id": job_id,
                "content_version": 1,
                "language": "en",
                "caption": "synthetic private content",
                "status": "proposal_only",
            },
            headers=_headers(**{"X-N8N-Execution-ID": "N8N-SYNTHETIC"}),
        )
        assert proposal.status_code == 202
        approved = client.post(
            f"/api/v1/social/jobs/{job_id}/approve",
            json={
                "approval_id": f"APR-{uuid4()}",
                "approved_by": "USR-SYNTHETIC",
                "content_version": 1,
            },
            headers=_headers(**{"X-Codestra-Role": "social_approver"}),
        )
        assert approved.status_code == 200
        scheduled = client.post(
            f"/api/v1/social/jobs/{job_id}/schedule", headers=_headers()
        )
        assert scheduled.status_code == 202
        assert scheduled.json()["mock"] is True
        assert (
            client.get(f"/api/v1/social/jobs/{job_id}", headers=_headers()).status_code
            == 200
        )


def test_auth_csrf_scope_validation_and_redaction(monkeypatch):
    _configure(monkeypatch)
    job_id = f"JOB-{uuid4()}"
    with TestClient(app) as client:
        missing = client.post("/api/v1/social/jobs", json=_job(job_id))
        assert missing.status_code == 401
        assert missing.headers["x-correlation-id"]
        expired = client.post(
            "/api/v1/social/jobs",
            json=_job(job_id),
            headers={"Authorization": "Bearer expired-session"},
        )
        assert expired.status_code == 401
        cookie_only = client.post(
            "/api/v1/social/jobs",
            json=_job(job_id),
            cookies={"session": "synthetic"},
            headers={"X-CSRF-Token": "synthetic"},
        )
        assert cookie_only.status_code == 401
        form = client.post("/api/v1/social/jobs", data=_job(job_id), headers=_headers())
        assert form.status_code == 422
        assert "location" not in form.headers
        mismatch = client.post(
            "/api/v1/social/jobs",
            json=_job(job_id),
            headers={**_headers(), "X-Organization-ID": "ORG-OTHER"},
        )
        assert mismatch.status_code == 403
        invalid = _job(job_id)
        invalid["caption"] = "token=must-not-be-reflected"
        rejected = client.post("/api/v1/social/jobs", json=invalid, headers=_headers())
        assert rejected.status_code == 422
        assert "must-not-be-reflected" not in rejected.text
        assert "caption" in rejected.text


def test_openapi_exposes_only_registered_social_methods(monkeypatch):
    _configure(monkeypatch)
    schema = app.openapi()
    social = {
        path: sorted(method for method in item if method in {"get", "post"})
        for path, item in schema["paths"].items()
        if path.startswith("/api/v1/social")
    }
    assert social == {
        "/api/v1/social/jobs": ["post"],
        "/api/v1/social/jobs/{job_id}": ["get"],
        "/api/v1/social/jobs/{job_id}/analytics": ["get"],
        "/api/v1/social/jobs/{job_id}/approve": ["post"],
        "/api/v1/social/jobs/{job_id}/audit": ["get"],
        "/api/v1/social/jobs/{job_id}/n8n-result": ["post"],
        "/api/v1/social/jobs/{job_id}/reconcile": ["post"],
        "/api/v1/social/jobs/{job_id}/retry": ["post"],
        "/api/v1/social/jobs/{job_id}/schedule": ["post"],
        "/api/v1/social/provider-events": ["post"],
    }
