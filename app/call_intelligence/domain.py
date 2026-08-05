from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class ProcessingPolicy(str, Enum):
    DISABLED = "CALL_RECORDING_PROCESSING_DISABLED"
    STAGING = "CALL_RECORDING_PROCESSING_STAGING"
    APPROVED = "CALL_RECORDING_PROCESSING_APPROVED"


class JobStatus(str, Enum):
    CALL_COMPLETED = "CALL_COMPLETED"
    RECORDING_PENDING = "RECORDING_PENDING"
    RECORDING_AVAILABLE = "RECORDING_AVAILABLE"
    TRANSCRIPTION_QUEUED = "TRANSCRIPTION_QUEUED"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIBED = "TRANSCRIBED"
    ANALYSIS_QUEUED = "ANALYSIS_QUEUED"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    QA_REVIEW_REQUIRED = "QA_REVIEW_REQUIRED"
    QA_REVIEWED = "QA_REVIEWED"
    ODOO_UPDATE_QUEUED = "ODOO_UPDATE_QUEUED"
    ODOO_UPDATING = "ODOO_UPDATING"
    COMPLETED = "COMPLETED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    CANCELLED = "CANCELLED"
    POLICY_BLOCKED = "POLICY_BLOCKED"


TRANSITIONS = {
    JobStatus.CALL_COMPLETED: {JobStatus.RECORDING_PENDING},
    JobStatus.RECORDING_PENDING: {
        JobStatus.RECORDING_AVAILABLE,
        JobStatus.RETRY_SCHEDULED,
        JobStatus.POLICY_BLOCKED,
    },
    JobStatus.RECORDING_AVAILABLE: {JobStatus.TRANSCRIPTION_QUEUED},
    JobStatus.TRANSCRIPTION_QUEUED: {JobStatus.TRANSCRIBING},
    JobStatus.TRANSCRIBING: {
        JobStatus.TRANSCRIBED,
        JobStatus.RETRY_SCHEDULED,
        JobStatus.FAILED,
        JobStatus.UNKNOWN,
    },
    JobStatus.TRANSCRIBED: {JobStatus.ANALYSIS_QUEUED},
    JobStatus.ANALYSIS_QUEUED: {JobStatus.ANALYZING},
    JobStatus.ANALYZING: {
        JobStatus.ANALYZED,
        JobStatus.RETRY_SCHEDULED,
        JobStatus.FAILED,
    },
    JobStatus.ANALYZED: {JobStatus.QA_REVIEW_REQUIRED, JobStatus.ODOO_UPDATE_QUEUED},
    JobStatus.QA_REVIEW_REQUIRED: {JobStatus.QA_REVIEWED},
    JobStatus.QA_REVIEWED: {JobStatus.ODOO_UPDATE_QUEUED},
    JobStatus.ODOO_UPDATE_QUEUED: {JobStatus.ODOO_UPDATING},
    JobStatus.ODOO_UPDATING: {
        JobStatus.COMPLETED,
        JobStatus.RETRY_SCHEDULED,
        JobStatus.FAILED,
        JobStatus.UNKNOWN,
    },
    JobStatus.RETRY_SCHEDULED: {
        JobStatus.RECORDING_PENDING,
        JobStatus.TRANSCRIPTION_QUEUED,
        JobStatus.ANALYSIS_QUEUED,
        JobStatus.ODOO_UPDATE_QUEUED,
        JobStatus.FAILED,
    },
}


class InvalidTransition(ValueError):
    pass


@dataclass
class AuditEvent:
    from_status: JobStatus
    to_status: JobStatus
    actor: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CallJob:
    tenant_id: UUID
    vicidial_uniqueid: str
    vicidial_call_id: str
    campaign_id: str
    agent_user: str
    id: UUID = field(default_factory=uuid4)
    status: JobStatus = JobStatus.CALL_COMPLETED
    audit: list[AuditEvent] = field(default_factory=list)

    @property
    def external_key(self) -> str:
        return f"codestra:{self.tenant_id}:call:{self.vicidial_uniqueid}"

    def transition(self, target: JobStatus, actor: str) -> None:
        if target in {JobStatus.CANCELLED}:
            pass
        elif target not in TRANSITIONS.get(self.status, set()):
            raise InvalidTransition(f"{self.status} -> {target} is not allowed")
        previous = self.status
        self.status = target
        self.audit.append(AuditEvent(previous, target, actor))


class IdempotencyStore:
    def __init__(self) -> None:
        self._jobs: dict[str, CallJob] = {}
        self._callbacks: set[str] = set()

    def create_job(self, job: CallJob) -> tuple[CallJob, bool]:
        existing = self._jobs.get(job.external_key)
        if existing:
            return existing, False
        self._jobs[job.external_key] = job
        return job, True

    def accept_callback(self, stage: str, job_id: UUID, payload: bytes) -> bool:
        digest = hashlib.sha256(payload).hexdigest()
        key = f"{stage}:{job_id}:{digest}"
        if key in self._callbacks:
            return False
        self._callbacks.add(key)
        return True


REDACTION_PATTERNS = {
    "PAYMENT_CARD": re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
    "SECURITY_CODE": re.compile(
        r"(?i)\b(?:cvv|cvc|security code)\s*(?:is|:)?\s*\d{3,6}\b"
    ),
    "SECRET": re.compile(r"(?i)\b(?:password|token|api[ _-]?key)\s*(?:is|:)?\s*\S+"),
    "BANK_ACCOUNT": re.compile(
        r"(?i)\b(?:account|iban)\s*(?:number|is|:)?\s*[A-Z0-9 -]{8,34}\b"
    ),
}


def redact_transcript(text: str) -> tuple[str, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    output = text
    for category, pattern in REDACTION_PATTERNS.items():

        def replace(match: re.Match[str]) -> str:
            events.append(
                {"type": category, "start": match.start(), "end": match.end()}
            )
            return f"[REDACTED:{category}]"

        output = pattern.sub(replace, output)
    return output, events
