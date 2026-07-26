import subprocess
import sys

from fastapi.testclient import TestClient

from app.core.config import settings
from app.entrypoints import (
    event_gateway,
    integration_api,
    notification_worker,
    scheduler,
    sync_worker,
)
from app.entrypoints.runtime import worker_app


def route_paths(app):
    return set(app.openapi()["paths"])


def test_api_surfaces_are_narrow_and_cover_existing_routes():
    event_paths = route_paths(event_gateway.app)
    integration_paths = route_paths(integration_api.app)
    assert "/api/v1/events/vicidial" in event_paths
    assert "/api/v2/telephony/canary" in event_paths
    assert "/api/v1/automation/events" in integration_paths
    assert "/webphone-api/v1/session" in integration_paths


def test_integration_api_excludes_event_gateway_routes_in_fresh_runtime():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.entrypoints.integration_api import app;"
                "paths=app.openapi()['paths'];"
                "assert not any(p.startswith('/api/v1/events/') for p in paths)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_api_runtime_health_and_correlation(monkeypatch):
    monkeypatch.setattr(settings, "middleware_secret", "unit-test-secret")
    response = TestClient(event_gateway.app).get(
        "/healthz", headers={"X-Correlation-ID": "synthetic-correlation"}
    )
    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == "synthetic-correlation"
    assert response.headers["Traceparent"].startswith("00-")


def test_disabled_delivery_workers_do_not_claim_or_contact_adapters(monkeypatch):
    monkeypatch.setattr(settings, "odoo_delivery_enabled", False)
    monkeypatch.setattr(settings, "n8n_delivery_enabled", False)
    monkeypatch.setattr(settings, "messaging_enabled", False)
    assert __import__("asyncio").run(sync_worker.cycle()) == {"status": "disabled"}
    assert __import__("asyncio").run(notification_worker.cycle()) == {
        "status": "disabled"
    }


def test_disabled_scheduler_is_safe(monkeypatch):
    monkeypatch.setattr(settings, "outbox_worker_enabled", False)
    assert __import__("asyncio").run(scheduler.cycle()) == {"status": "disabled"}


def test_worker_has_internal_operational_endpoints():
    app = worker_app("test-worker", "test.queue.v1", sync_worker.cycle)
    paths = route_paths(app)
    assert {"/healthz", "/readyz", "/dependencies"} <= paths
