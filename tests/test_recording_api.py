from datetime import UTC, datetime, timedelta

import pytest

from app.core.recordings import ObjectHead, RecordingService


class Store:
    head_value = ObjectHead(9, "a" * 64, "audio/mpeg", "version-1")

    def reserve(self, opaque_id, expires_in):
        return f"https://storage.invalid/upload/{opaque_id}", datetime.now(UTC) + timedelta(seconds=expires_in)

    def head(self, opaque_id):
        return self.head_value

    def playback(self, opaque_id, expires_in):
        return f"https://storage.invalid/play/{opaque_id}", datetime.now(UTC) + timedelta(seconds=expires_in)


class Odoo:
    calls = 0
    def upsert(self, payload):
        self.calls += 1
        return "ODOO-OPAQUE"


def payload(**updates):
    value = {
        "idempotency_key": "k" * 64, "environment": "staging",
        "recording_uid": "REC-" + "a" * 32,
        "campaign_id": "SYNTHETIC", "sha256": "a" * 64,
        "size_bytes": 9, "content_type": "audio/mpeg",
        "vicidial_recording_id": "42",
        "vicidial_call_id": "call_fixture",
        "asterisk_uniqueid": "asterisk_fixture",
        "duration_seconds": 1.0,
        "format": "mp3",
        "codec": "mp3",
        "channels": 1,
        "sample_rate_hz": 8000,
    }
    value.update(updates)
    return value


def test_mtls_reservation_and_idempotent_completion():
    odoo = Odoo()
    service = RecordingService(Store(), odoo, odoo_write_enabled=True)
    first = service.reserve(payload(), "server-b-recording-exporter")
    second = service.reserve(payload(), "server-b-recording-exporter")
    assert first["recording_uid"] == second["recording_uid"]
    result = service.complete(first["recording_uid"], {
        "environment": "staging", "campaign_id": "SYNTHETIC",
        "idempotency_key": "k" * 64, "duration_seconds": 1.0, "format": "mp3",
    }, "server-b-recording-exporter")
    assert result["state"] == "ODOO_LINKED"
    assert result["checksum_verified"] is True
    assert result["odoo_linked"] is True
    service.complete(first["recording_uid"], {
        "environment": "staging", "campaign_id": "SYNTHETIC",
        "idempotency_key": "k" * 64, "duration_seconds": 1.0, "format": "mp3",
    }, "server-b-recording-exporter")
    assert odoo.calls == 1


def test_wrong_identity_environment_and_checksum_fail_closed():
    service = RecordingService(Store(), Odoo())
    with pytest.raises(PermissionError):
        service.reserve(payload(), "wrong-client")
    with pytest.raises(ValueError):
        service.reserve(payload(environment="production"), "server-b-recording-exporter")
    reserved = service.reserve(payload(), "server-b-recording-exporter")
    service.store.head_value = ObjectHead(9, "b" * 64, "audio/mpeg", "version-1")
    with pytest.raises(ValueError, match="checksum"):
        service.complete(reserved["recording_uid"], {
            "environment": "staging", "campaign_id": "SYNTHETIC",
            "idempotency_key": "k" * 64, "duration_seconds": 1.0,
            "format": "mp3",
        }, "server-b-recording-exporter")


def test_playback_requires_verified_link_and_authorization():
    service = RecordingService(Store(), Odoo())
    reserved = service.reserve(payload(), "server-b-recording-exporter")
    with pytest.raises(PermissionError):
        service.playback(reserved["recording_uid"], True)


def test_status_requires_approved_mtls_peer():
    service = RecordingService(Store(), Odoo())
    reserved = service.reserve(payload(), "server-b-recording-exporter")
    with pytest.raises(PermissionError):
        service.status(reserved["recording_uid"], "unknown")
    assert service.status(
        reserved["recording_uid"], "recording-retention-worker"
    )["state"] == "RESERVED"


def test_odoo_recording_write_is_disabled_by_default():
    odoo = Odoo()
    service = RecordingService(Store(), odoo)
    reserved = service.reserve(payload(), "server-b-recording-exporter")
    result = service.complete(reserved["recording_uid"], {
        "environment": "staging", "campaign_id": "SYNTHETIC",
        "idempotency_key": "k" * 64, "duration_seconds": 1.0, "format": "mp3",
    }, "server-b-recording-exporter")
    assert result == {
        "recording_uid": reserved["recording_uid"],
        "state": "VERIFIED",
        "checksum_verified": True,
        "odoo_linked": False,
    }
    assert odoo.calls == 0
