from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class RecordingState(str, Enum):
    RESERVATION_PENDING = "RESERVATION_PENDING"
    RESERVED = "RESERVED"
    UPLOAD_PENDING = "UPLOAD_PENDING"
    UPLOADED = "UPLOADED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    ODOO_LINK_PENDING = "ODOO_LINK_PENDING"
    ODOO_LINKED = "ODOO_LINKED"
    RETENTION_PENDING = "RETENTION_PENDING"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ObjectHead:
    size_bytes: int
    content_type: str
    checksum_sha256: str
    version_id: str
    metadata: dict[str, str]


@dataclass
class Recording:
    recording_uid: str
    environment: str
    campaign_key: str
    call_uid: str
    idempotency_key: str
    sha256: str
    size_bytes: int
    content_type: str
    opaque_object_identifier: str
    retention_class: str
    duration_seconds: float | None = None
    state: RecordingState = RecordingState.RESERVATION_PENDING
    object_version_id: str | None = None
    verified_at: datetime | None = None
    odoo_linked_at: datetime | None = None
    legal_hold: bool = False
    failure_code: str | None = None
    automation_results: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class StateAudit:
    recording_uid: str
    sequence: int
    from_state: str | None
    to_state: str
    reason: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class RecordingConflict(RuntimeError):
    pass


class RecordingNotFound(LookupError):
    pass
