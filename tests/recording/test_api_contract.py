from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app

SHA = "a" * 64


def reservation_payload():
    return {
        "contract_version": "1.0",
        "idempotency_key": "c" * 64,
        "recording": {
            "contract_version": "1.0",
            "vicidial_recording_id": "9001",
            "vicidial_call_id": "call-contract",
            "asterisk_uniqueid": "asterisk-contract",
            "campaign_key": "SYNTHETIC",
            "agent_key": "agent-contract",
            "started_at": "2026-07-31T00:00:00Z",
            "duration_seconds": 1.25,
            "format": "mp3",
            "codec": "mp3",
            "channels": 1,
            "sample_rate_hz": 8000,
            "file_size_bytes": 123,
            "sha256": SHA,
            "environment": "staging",
            "retention_class": "synthetic_test",
        },
    }


def exporter_headers(nonce: str):
    return {
        "X-TLS-Client-Identity": "codestra-recording-exporter-server-b",
        "X-Certificate-Environment": "staging",
        "X-Certificate-Role": "recording-exporter",
        "X-Audience": "codestra-recording-api",
        "X-TLS-Client-Not-After": (
            datetime.now(UTC) + timedelta(days=1)
        ).isoformat(),
        "X-TLS-Client-Revoked": "false",
        "X-Request-Nonce": nonce,
        "X-Request-Timestamp": str(int(datetime.now(UTC).timestamp())),
    }


def test_exporter_mtls_is_required_and_middleware_assigns_uid():
    client = TestClient(app)
    assert client.post(
        "/api/v1/recordings/reservations", json=reservation_payload()
    ).status_code == 401
    response = client.post(
        "/api/v1/recordings/reservations",
        json=reservation_payload(),
        headers=exporter_headers("reservation-contract-nonce"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["contract_version"] == "1.0"
    assert body["recording_uid"].startswith("REC-")
    assert "recording_uid" not in reservation_payload()["recording"]


def test_reservation_is_deterministic_and_replay_is_rejected():
    client = TestClient(app)
    first = client.post(
        "/api/v1/recordings/reservations",
        json=reservation_payload(),
        headers=exporter_headers("deterministic-first"),
    )
    second = client.post(
        "/api/v1/recordings/reservations",
        json=reservation_payload(),
        headers=exporter_headers("deterministic-second"),
    )
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    replay_headers = exporter_headers("replayed-nonce")
    accepted = client.post(
        "/api/v1/recordings/reservations",
        json={**reservation_payload(), "idempotency_key": "d" * 64},
        headers=replay_headers,
    )
    rejected = client.post(
        "/api/v1/recordings/reservations",
        json={**reservation_payload(), "idempotency_key": "e" * 64},
        headers=replay_headers,
    )
    assert accepted.status_code == 201
    assert rejected.status_code == 401


def test_health_and_service_identity_contract():
    client = TestClient(app)
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code in {200, 503}
    identity = client.get("/.well-known/codestra-service")
    assert identity.status_code == 200
    assert identity.json()["hostname"] == "api.staging.internal.codestra.agency"
    assert identity.json()["tls_sni_required"] is True
