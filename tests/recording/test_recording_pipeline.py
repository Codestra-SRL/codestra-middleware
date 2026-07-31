from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.recording.domain import ObjectHead, RecordingConflict, RecordingState
from app.recording.odoo import AcknowledgingOdooClient
from app.recording.security import (
    AuthenticationError,
    ExporterIdentity,
    MTLSAuthorizer,
    ReplayGuard,
)
from app.recording.service import RecordingService
from app.recording.storage import MemoryObjectStorage

SHA = "a" * 64


def reservation(**updates):
    payload = {
        "environment": "staging",
        "campaign_key": "SYNTHETIC",
        "call_uid": "call-fixture",
        "idempotency_key": "fixture-idempotency-key",
        "sha256": SHA,
        "size_bytes": 123,
        "content_type": "audio/mpeg",
        "retention_class": "synthetic_test",
        "duration_seconds": 1.5,
    }
    payload.update(updates)
    return payload


def setup_object(service, response, **metadata_updates):
    recording = service.get(response["recording_uid"])
    metadata = {
        "environment": recording.environment,
        "campaign_key": recording.campaign_key,
        "recording_uid": recording.recording_uid,
        "idempotency_key": recording.idempotency_key,
    }
    metadata.update(metadata_updates)
    service.storage.objects[(recording.opaque_object_identifier, "v1")] = ObjectHead(
        123, "audio/mpeg", SHA, "v1", metadata
    )


def test_mtls_role_audience_environment_and_replay_gate():
    auth = MTLSAuthorizer({"spiffe://codestra/server-b": "staging"})
    auth.authorize(
        ExporterIdentity(
            "spiffe://codestra/server-b",
            "staging",
            "server-b-recording-exporter",
            "codestra-recording-api",
        )
    )
    with pytest.raises(AuthenticationError):
        auth.authorize(
            ExporterIdentity(
                "spiffe://codestra/server-b",
                "production",
                "server-b-recording-exporter",
                "codestra-recording-api",
            )
        )
    replay = ReplayGuard()
    now = 1_800_000_000
    replay.consume("unique-nonce", now, now)
    with pytest.raises(AuthenticationError):
        replay.consume("unique-nonce", now, now)


@pytest.mark.asyncio
async def test_reservation_verification_odoo_ack_duplicate_and_event():
    service = RecordingService(MemoryObjectStorage(), AcknowledgingOdooClient())
    first = service.reserve(reservation())
    duplicate = service.reserve(reservation())
    assert duplicate["recording_uid"] == first["recording_uid"]
    assert duplicate["duplicate"] is True
    assert first["upload_url_expires_at"]
    assert "credentials" not in first and "object_key" not in first
    setup_object(service, first)
    ack = await service.complete(first["recording_uid"], {"object_version_id": "v1"})
    assert ack["checksum_verified"] and ack["odoo_linked"]
    assert service.get(first["recording_uid"]).state == RecordingState.RETENTION_PENDING
    assert service.outbox[0]["binding_enabled"] is False
    assert "telephone_number" not in service.outbox[0]
    replay = await service.complete(
        first["recording_uid"], {"object_version_id": "v1"}
    )
    assert replay["duplicate"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata_update",
    [
        {"environment": "production"},
        {"campaign_key": "WRONG"},
        {"recording_uid": "REC-wrong"},
        {"idempotency_key": "wrong-idempotency-key"},
    ],
)
async def test_metadata_mismatch_quarantines(metadata_update):
    service = RecordingService(MemoryObjectStorage(), AcknowledgingOdooClient())
    response = service.reserve(reservation())
    setup_object(service, response, **metadata_update)
    with pytest.raises(RecordingConflict):
        await service.complete(response["recording_uid"], {"object_version_id": "v1"})
    assert service.get(response["recording_uid"]).state == RecordingState.QUARANTINED


@pytest.mark.asyncio
async def test_size_checksum_content_type_and_version_are_verified():
    for field, value in (
        ("size_bytes", 124),
        ("checksum_sha256", "b" * 64),
        ("content_type", "audio/wav"),
        ("version_id", "other"),
    ):
        service = RecordingService(MemoryObjectStorage(), AcknowledgingOdooClient())
        response = service.reserve(reservation())
        recording = service.get(response["recording_uid"])
        head = ObjectHead(
            123,
            "audio/mpeg",
            SHA,
            "v1",
            {
                "environment": "staging",
                "campaign_key": "SYNTHETIC",
                "recording_uid": recording.recording_uid,
                "idempotency_key": recording.idempotency_key,
            },
        )
        object.__setattr__(head, field, value)
        service.storage.objects[(recording.opaque_object_identifier, "v1")] = head
        with pytest.raises(RecordingConflict):
            await service.complete(
                recording.recording_uid, {"object_version_id": "v1"}
            )


class FailingOdoo:
    async def upsert(self, metadata, idempotency_key):
        raise RuntimeError("temporary Odoo failure")


@pytest.mark.asyncio
async def test_odoo_ack_required_and_retry_state_never_links_early():
    service = RecordingService(MemoryObjectStorage(), FailingOdoo())
    response = service.reserve(reservation())
    setup_object(service, response)
    with pytest.raises(RuntimeError):
        await service.complete(response["recording_uid"], {"object_version_id": "v1"})
    recording = service.get(response["recording_uid"])
    assert recording.state == RecordingState.ODOO_LINK_PENDING
    assert recording.odoo_linked_at is None
    assert service.outbox == []


@pytest.mark.asyncio
async def test_playback_scope_ttl_nonpersistence_and_retention_gates():
    service = RecordingService(MemoryObjectStorage(), AcknowledgingOdooClient())
    response = service.reserve(reservation())
    setup_object(service, response)
    await service.complete(response["recording_uid"], {"object_version_id": "v1"})
    with pytest.raises(PermissionError):
        service.playback_url(
            response["recording_uid"], scope_authorized=False, ttl_seconds=120
        )
    body = service.playback_url(
        response["recording_uid"], scope_authorized=True, ttl_seconds=120
    )
    assert body["expires_in"] <= 120
    assert service.playback_urls_persisted == 0
    recording = service.get(response["recording_uid"])
    before = service.retention_decision(
        response["recording_uid"], recording.verified_at + timedelta(days=6)
    )
    assert not before.eligible
    after = service.retention_decision(
        response["recording_uid"], recording.verified_at + timedelta(days=8)
    )
    assert after.eligible and not after.delete_executed
    recording.legal_hold = True
    assert not service.retention_decision(
        response["recording_uid"], datetime.now(UTC) + timedelta(days=100)
    ).eligible


def test_automation_result_idempotent_and_authority_protected():
    service = RecordingService(MemoryObjectStorage(), AcknowledgingOdooClient())
    response = service.reserve(reservation())
    result = {"transcription_status": "submitted"}
    first = service.automation_result(
        response["recording_uid"], "automation-result-key", result
    )
    second = service.automation_result(
        response["recording_uid"], "automation-result-key", result
    )
    assert first["duplicate"] is False and second["duplicate"] is True
    with pytest.raises(RecordingConflict):
        service.automation_result(
            response["recording_uid"], "different-result-key", {"sha256": "x"}
        )
