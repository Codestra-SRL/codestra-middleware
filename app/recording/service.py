from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from .domain import (
    Recording,
    RecordingConflict,
    RecordingNotFound,
    RecordingState,
    StateAudit,
)
from .odoo import OdooRecordingPort
from .retention import RetentionDecision, RetentionEngine
from .storage import PrivateObjectStorage


class RecordingService:
    def __init__(
        self, storage: PrivateObjectStorage, odoo: OdooRecordingPort
    ) -> None:
        self.storage = storage
        self.odoo = odoo
        self.retention = RetentionEngine()
        self.recordings: dict[str, Recording] = {}
        self.by_idempotency: dict[tuple[str, str], str] = {}
        self.object_versions: dict[str, str] = {}
        self.audit: list[StateAudit] = []
        self.outbox: list[dict[str, Any]] = []
        self.playback_urls_persisted = 0

    def _transition(
        self, recording: Recording, state: RecordingState, reason: str
    ) -> None:
        previous = recording.state
        recording.state = state
        self.audit.append(
            StateAudit(
                recording.recording_uid,
                len([a for a in self.audit if a.recording_uid == recording.recording_uid])
                + 1,
                previous.value,
                state.value,
                reason,
            )
        )

    def reserve(self, payload: dict[str, Any]) -> dict[str, Any]:
        key = (payload["environment"], payload["idempotency_key"])
        if key in self.by_idempotency:
            existing = self.recordings[self.by_idempotency[key]]
            url, expires = self.storage.reserve_upload(
                existing.opaque_object_identifier,
                existing.content_type,
                existing.sha256,
                300,
            )
            return self._reservation_response(existing, url, expires, True)
        uid = f"REC-{uuid.uuid4().hex}"
        opaque = uuid.uuid4().hex
        recording = Recording(
            recording_uid=uid,
            environment=payload["environment"],
            campaign_key=payload["campaign_key"],
            call_uid=payload["call_uid"],
            idempotency_key=payload["idempotency_key"],
            sha256=payload["sha256"],
            size_bytes=payload["size_bytes"],
            content_type=payload["content_type"],
            opaque_object_identifier=opaque,
            retention_class=payload.get("retention_class", "standard"),
            duration_seconds=payload.get("duration_seconds"),
        )
        self.recordings[uid] = recording
        self.by_idempotency[key] = uid
        self._transition(recording, RecordingState.RESERVED, "reservation_created")
        self._transition(recording, RecordingState.UPLOAD_PENDING, "upload_authorized")
        url, expires = self.storage.reserve_upload(
            opaque, recording.content_type, recording.sha256, 300
        )
        return self._reservation_response(recording, url, expires, False)

    @staticmethod
    def _reservation_response(
        recording: Recording, url: str, expires: datetime, duplicate: bool
    ) -> dict[str, Any]:
        return {
            "recording_uid": recording.recording_uid,
            "upload_url": url,
            "upload_url_expires_at": expires.isoformat(),
            "required_checksum_header": "x-amz-checksum-sha256",
            "required_content_type": recording.content_type,
            "opaque_object_identifier": recording.opaque_object_identifier,
            "duplicate": duplicate,
        }

    def get(self, recording_uid: str) -> Recording:
        try:
            return self.recordings[recording_uid]
        except KeyError as exc:
            raise RecordingNotFound(recording_uid) from exc

    async def complete(
        self, recording_uid: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        recording = self.get(recording_uid)
        version_id = payload["object_version_id"]
        if (
            recording.state == RecordingState.RETENTION_PENDING
            and recording.object_version_id == version_id
        ):
            return self._ack(recording, duplicate=True)
        if recording.state not in {
            RecordingState.UPLOAD_PENDING,
            RecordingState.UPLOADED,
            RecordingState.VERIFYING,
            RecordingState.ODOO_LINK_PENDING,
        }:
            raise RecordingConflict("completion conflicts with recording state")
        owner = self.object_versions.get(version_id)
        if owner is not None and owner != recording_uid:
            self._transition(recording, RecordingState.QUARANTINED, "version_conflict")
            raise RecordingConflict("object version already belongs to another recording")
        self._transition(recording, RecordingState.UPLOADED, "completion_received")
        self._transition(recording, RecordingState.VERIFYING, "object_head_requested")
        try:
            head = self.storage.head(recording.opaque_object_identifier, version_id)
        except (KeyError, OSError):
            self._transition(recording, RecordingState.FAILED, "object_head_failed")
            raise RecordingConflict("object unavailable")
        expected = {
            "sha256": recording.sha256,
            "size_bytes": recording.size_bytes,
            "content_type": recording.content_type,
            "version_id": version_id,
            "environment": recording.environment,
            "campaign_key": recording.campaign_key,
            "recording_uid": recording.recording_uid,
            "idempotency_key": recording.idempotency_key,
        }
        actual = {
            "sha256": head.checksum_sha256,
            "size_bytes": head.size_bytes,
            "content_type": head.content_type,
            "version_id": head.version_id,
            "environment": head.metadata.get("environment"),
            "campaign_key": head.metadata.get("campaign_key"),
            "recording_uid": head.metadata.get("recording_uid"),
            "idempotency_key": head.metadata.get("idempotency_key"),
        }
        mismatches = sorted(k for k in expected if expected[k] != actual[k])
        if mismatches:
            recording.failure_code = "OBJECT_METADATA_MISMATCH"
            self._transition(
                recording, RecordingState.QUARANTINED, ",".join(mismatches)
            )
            raise RecordingConflict("object verification mismatch")
        recording.object_version_id = version_id
        recording.verified_at = datetime.now(UTC)
        self.object_versions[version_id] = recording_uid
        self._transition(recording, RecordingState.VERIFIED, "object_verified")
        self._transition(
            recording, RecordingState.ODOO_LINK_PENDING, "odoo_upsert_requested"
        )
        metadata = {
            "recording_uid": recording.recording_uid,
            "environment": recording.environment,
            "campaign_key": recording.campaign_key,
            "call_uid": recording.call_uid,
            "duration_seconds": recording.duration_seconds,
            "sha256": recording.sha256,
            "size_bytes": recording.size_bytes,
            "content_type": recording.content_type,
            "object_version_id": version_id,
            "retention_class": recording.retention_class,
        }
        try:
            acknowledgement = await self.odoo.upsert(
                metadata, recording.idempotency_key
            )
        except Exception:
            recording.failure_code = "ODOO_UPSERT_FAILED"
            raise
        if acknowledgement.get("acknowledged") is not True:
            raise RecordingConflict("Odoo acknowledgement required")
        recording.odoo_linked_at = datetime.now(UTC)
        self._transition(recording, RecordingState.ODOO_LINKED, "odoo_acknowledged")
        self._transition(
            recording, RecordingState.RETENTION_PENDING, "retention_calculation_pending"
        )
        self.outbox.append(self._verified_event(recording))
        return self._ack(recording, duplicate=False)

    @staticmethod
    def _ack(recording: Recording, duplicate: bool) -> dict[str, Any]:
        return {
            "recording_uid": recording.recording_uid,
            "state": recording.state.value,
            "checksum_verified": recording.verified_at is not None,
            "odoo_linked": recording.odoo_linked_at is not None,
            "duplicate": duplicate,
        }

    @staticmethod
    def _verified_event(recording: Recording) -> dict[str, Any]:
        return {
            "binding_key": "n8n.events.ingest",
            "binding_enabled": False,
            "event_id": str(uuid.uuid4()),
            "event_type": "vicidial.recording.verified.v1",
            "occurred_at": datetime.now(UTC).isoformat(),
            "environment": recording.environment,
            "recording_uid": recording.recording_uid,
            "call_uid": recording.call_uid,
            "campaign_key": recording.campaign_key,
            "duration_seconds": recording.duration_seconds,
            "sha256": recording.sha256,
            "object_version_id": recording.object_version_id,
            "retention_class": recording.retention_class,
        }

    def failure(self, recording_uid: str, code: str) -> dict[str, Any]:
        recording = self.get(recording_uid)
        recording.failure_code = code
        self._transition(recording, RecordingState.FAILED, code)
        return self._ack(recording, duplicate=False)

    def playback_url(
        self,
        recording_uid: str,
        *,
        scope_authorized: bool,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        recording = self.get(recording_uid)
        if not scope_authorized:
            raise PermissionError("playback scope denied")
        if (
            recording.state != RecordingState.RETENTION_PENDING
            or not recording.object_version_id
            or recording.legal_hold
        ):
            raise PermissionError("recording is not playable")
        ttl = min(ttl_seconds, 120)
        url = self.storage.presign_read(
            recording.opaque_object_identifier, recording.object_version_id, ttl
        )
        return {"playback_url": url, "expires_in": ttl}

    def automation_result(
        self, recording_uid: str, idempotency_key: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        recording = self.get(recording_uid)
        forbidden = {
            "sha256",
            "checksum",
            "object_version_id",
            "object_key",
            "retention_class",
            "legal_hold",
        }
        if forbidden.intersection(result):
            raise RecordingConflict("automation result cannot mutate authority")
        duplicate = idempotency_key in recording.automation_results
        recording.automation_results.setdefault(idempotency_key, result)
        return {"accepted": True, "duplicate": duplicate}

    def retention_decision(
        self, recording_uid: str, now: datetime | None = None
    ) -> RetentionDecision:
        return self.retention.decide(self.get(recording_uid), now)
