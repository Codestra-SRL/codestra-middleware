"""Recording reservation domain with fail-closed object verification."""
from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class ObjectHead:
    size_bytes: int
    checksum_sha256: str
    content_type: str
    version_id: str


class ObjectStore(Protocol):
    def reserve(self, opaque_id: str, expires_in: int) -> tuple[str, datetime]: ...
    def head(self, opaque_id: str) -> ObjectHead: ...
    def playback(self, opaque_id: str, expires_in: int) -> tuple[str, datetime]: ...


class OdooRecordingWriter(Protocol):
    def upsert(self, payload: dict[str, Any]) -> str: ...


@dataclass
class Recording:
    uid: str
    idempotency_key: str
    environment: str
    campaign_id: str
    opaque_object_id: str
    expected_sha256: str
    expected_size: int
    content_type: str
    vicidial_recording_id: str
    vicidial_call_id: str
    asterisk_uniqueid: str
    duration_seconds: float
    format: str
    codec: str
    channels: int
    sample_rate_hz: int
    state: str = "RESERVED"
    object_version: str | None = None
    odoo_reference: str | None = None
    failures: list[str] = field(default_factory=list)


class RecordingService:
    def __init__(self, store: ObjectStore, odoo: OdooRecordingWriter) -> None:
        self.store = store
        self.odoo = odoo
        self.by_uid: dict[str, Recording] = {}
        self.by_key: dict[str, str] = {}

    def reserve(self, payload: dict[str, Any], peer: str) -> dict[str, object]:
        if peer != "server-b-recording-exporter":
            raise PermissionError("untrusted mTLS service identity")
        if payload.get("environment") != "staging":
            raise ValueError("environment mismatch")
        key = str(payload["idempotency_key"])
        if key in self.by_key:
            recording = self.by_uid[self.by_key[key]]
            expected = (
                recording.uid,
                recording.expected_sha256,
                recording.expected_size,
                recording.campaign_id,
            )
            observed = (
                str(payload["recording_uid"]),
                str(payload["sha256"]),
                int(payload["size_bytes"]),
                str(payload["campaign_id"]),
            )
            if observed != expected:
                raise ValueError("idempotency payload conflict")
        else:
            uid = str(payload["recording_uid"])
            if uid in self.by_uid:
                raise ValueError("recording UID conflict")
            opaque = secrets.token_urlsafe(24)
            recording = Recording(
                uid=uid,
                idempotency_key=key,
                environment="staging",
                campaign_id=str(payload["campaign_id"]),
                opaque_object_id=opaque,
                expected_sha256=str(payload["sha256"]),
                expected_size=int(payload["size_bytes"]),
                content_type=str(payload["content_type"]),
                vicidial_recording_id=str(payload["vicidial_recording_id"]),
                vicidial_call_id=str(payload["vicidial_call_id"]),
                asterisk_uniqueid=str(payload["asterisk_uniqueid"]),
                duration_seconds=float(payload["duration_seconds"]),
                format=str(payload["format"]),
                codec=str(payload["codec"]),
                channels=int(payload["channels"]),
                sample_rate_hz=int(payload["sample_rate_hz"]),
            )
            self.by_uid[uid] = recording
            self.by_key[key] = uid
        url, expiry = self.store.reserve(recording.opaque_object_id, 300)
        return {
            "recording_uid": recording.uid,
            "upload_url": url,
            "upload_url_expires_at": expiry.isoformat(),
            "required_checksum_header": "x-amz-checksum-sha256",
            "required_content_type": recording.content_type,
            "opaque_object_identifier": recording.opaque_object_id,
        }

    def complete(
        self, uid: str, payload: dict[str, Any], peer: str
    ) -> dict[str, str | bool]:
        if peer != "server-b-recording-exporter":
            raise PermissionError("untrusted mTLS service identity")
        recording = self.by_uid[uid]
        if recording.state == "ODOO_LINKED":
            return {
                "recording_uid": uid,
                "state": recording.state,
                "checksum_verified": True,
                "odoo_linked": True,
            }
        if payload.get("environment") != recording.environment:
            raise ValueError("environment mismatch")
        if payload.get("campaign_id") != recording.campaign_id:
            raise ValueError("campaign mismatch")
        if payload.get("idempotency_key") != recording.idempotency_key:
            raise ValueError("idempotency key mismatch")
        if float(payload.get("duration_seconds", -1)) != recording.duration_seconds:
            raise ValueError("duration mismatch")
        if payload.get("format") != recording.format:
            raise ValueError("format mismatch")
        head = self.store.head(recording.opaque_object_id)
        if not hmac.compare_digest(head.checksum_sha256, recording.expected_sha256):
            raise ValueError("checksum mismatch")
        if head.size_bytes != recording.expected_size:
            raise ValueError("size mismatch")
        if head.content_type != recording.content_type or not head.version_id:
            raise ValueError("object identity mismatch")
        recording.object_version = head.version_id
        recording.state = "VERIFIED"
        recording.odoo_reference = self.odoo.upsert({
            "recording_uid": uid,
            "object_version_id": head.version_id,
            "campaign_id": recording.campaign_id,
            "vicidial_recording_id": recording.vicidial_recording_id,
            "vicidial_call_id": recording.vicidial_call_id,
            "asterisk_uniqueid": recording.asterisk_uniqueid,
            "duration_seconds": recording.duration_seconds,
            "format": recording.format,
            "codec": recording.codec,
            "channels": recording.channels,
            "sample_rate_hz": recording.sample_rate_hz,
            "checksum_sha256": recording.expected_sha256,
            "size_bytes": recording.expected_size,
        })
        recording.state = "ODOO_LINKED"
        return {
            "recording_uid": uid,
            "state": recording.state,
            "checksum_verified": True,
            "odoo_linked": True,
        }

    def failure(self, uid: str, code: str, peer: str) -> dict[str, str]:
        if peer != "server-b-recording-exporter":
            raise PermissionError("untrusted mTLS service identity")
        self.by_uid[uid].failures.append(code[:64])
        return {"recording_uid": uid, "state": self.by_uid[uid].state}

    def playback(self, uid: str, authorized: bool) -> dict[str, str]:
        recording = self.by_uid[uid]
        if not authorized or recording.state != "ODOO_LINKED":
            raise PermissionError("playback denied")
        url, expiry = self.store.playback(recording.opaque_object_id, 120)
        return {"playback_url": url, "expires_at": expiry.isoformat()}

    def status(self, uid: str, peer: str) -> dict[str, str]:
        if peer not in {
            "server-b-recording-exporter",
            "odoo-recording-service",
            "recording-retention-worker",
        }:
            raise PermissionError("untrusted mTLS service identity")
        recording = self.by_uid[uid]
        return {"recording_uid": recording.uid, "state": recording.state}
