"""Fail-closed Postly social publishing control plane used by the mock adapter.

This module deliberately contains no Postly credential or network client.  It is
the executable reference for lifecycle, approval, idempotency, retry and
reconciliation semantics before the durable/provider implementation is enabled.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class SocialError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class SocialState(str, Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "unknown_requires_reconciliation"


@dataclass(frozen=True)
class Approval:
    approval_id: str
    approved_by: str
    approved_at: datetime
    content_version: int


@dataclass(frozen=True)
class AuditRecord:
    sequence: int
    action: str
    from_state: str | None
    to_state: str
    actor_ref: str
    occurred_at: datetime
    safe_details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SocialJob:
    organization_id: str
    workspace_id: str
    campaign_id: str
    content_job_id: str
    content_version: int
    integration_ids: tuple[str, ...]
    scheduled_at: datetime
    preferred_language: str
    correlation_id: str
    state: SocialState = SocialState.DRAFT
    caption: str | None = None
    approval: Approval | None = None
    provider_group_id: str | None = None
    provider_results: list[dict[str, Any]] = field(default_factory=list)
    attempts: int = 0
    next_attempt_at: datetime | None = None
    last_error_category: str | None = None
    audit: list[AuditRecord] = field(default_factory=list)


class MockPostlyAdapter:
    """Deterministic adapter with injectable failures and provider readback."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self.now = now
        self.posts: dict[str, dict[str, Any]] = {}
        self.calls = 0
        self.fail_next: str | None = None

    def schedule(self, command: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        failure, self.fail_next = self.fail_next, None
        if failure == "temporary":
            raise SocialError("POSTLY_TEMPORARY", "temporary provider failure", 503)
        if failure == "timeout_after_write":
            result = self._create(command)
            self.posts[result["postly_group_id"]] = result
            raise SocialError("POSTLY_TIMEOUT", "provider outcome uncertain", 504)
        return self._create(command)

    def _create(self, command: dict[str, Any]) -> dict[str, Any]:
        group_id = str(uuid4())
        result = {
            "event_id": command["event_id"],
            "correlation_id": command["correlation_id"],
            "state": "scheduled",
            "occurred_at": self.now().isoformat(),
            "postly_group_id": group_id,
            "provider_results": [
                {
                    "integration_id": integration_id,
                    "state": "scheduled",
                    "provider_release_id": None,
                    "error": None,
                }
                for integration_id in command["integration_ids"]
            ],
            "error": None,
        }
        self.posts[group_id] = result
        return result

    def find(self, command: dict[str, Any]) -> dict[str, Any] | None:
        integration_ids = {item for item in command["integration_ids"]}
        for result in self.posts.values():
            if {
                x["integration_id"] for x in result["provider_results"]
            } == integration_ids:
                return result
        return None

    def analytics(self, group_id: str) -> dict[str, int]:
        if group_id not in self.posts:
            raise SocialError("POSTLY_NOT_FOUND", "provider post not found", 404)
        return {"impressions": 0, "reactions": 0, "comments": 0, "shares": 0}


class SocialControlPlane:
    RETRYABLE = frozenset({"rate_limit", "temporary"})

    def __init__(self, *, now: Callable[[], datetime] | None = None) -> None:
        self.now = now or (lambda: datetime.now(timezone.utc))  # noqa: UP017
        self.adapter = MockPostlyAdapter(self.now)
        self.jobs: dict[str, SocialJob] = {}
        self.claims: dict[str, str] = {}

    def _transition(
        self, job: SocialJob, state: SocialState, action: str, actor: str, **safe: Any
    ) -> None:
        previous = job.state
        job.state = state
        job.audit.append(
            AuditRecord(
                len(job.audit) + 1, action, previous, state, actor, self.now(), safe
            )
        )

    @staticmethod
    def claim_key(job: SocialJob) -> str:
        raw = "|".join(
            (
                job.organization_id,
                job.content_job_id,
                str(job.content_version),
                *job.integration_ids,
                job.scheduled_at.isoformat(),
            )
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def create(self, request: dict[str, Any]) -> SocialJob:
        job_id = request["content_job_id"]
        existing = self.jobs.get(job_id)
        if existing:
            return existing
        scheduled_at = datetime.fromisoformat(
            request["scheduled_at"].replace("Z", "+00:00")  # noqa: FURB162
        )
        job = SocialJob(
            organization_id=request["organization_id"],
            workspace_id=request["workspace_id"],
            campaign_id=request["campaign_id"],
            content_job_id=job_id,
            content_version=request["content_version"],
            integration_ids=tuple(request["integration_ids"]),
            scheduled_at=scheduled_at,
            preferred_language=request.get("preferred_language", "en"),
            correlation_id=request["correlation_id"],
        )
        self.jobs[job_id] = job
        self._transition(job, SocialState.GENERATING, "n8n_generation_queued", "odoo")
        return job

    def accept_n8n_proposal(self, job_id: str, proposal: dict[str, Any]) -> SocialJob:
        job = self._get(job_id)
        if (
            proposal.get("content_job_id") != job_id
            or proposal.get("content_version") != job.content_version
        ):
            raise SocialError("STALE_N8N_RESULT", "n8n result binding conflict")
        if proposal.get("status") != "proposal_only" or not isinstance(
            proposal.get("caption"), str
        ):
            raise SocialError(
                "INVALID_N8N_RESULT", "invalid generated-content result", 422
            )
        job.caption = proposal["caption"]
        self._transition(
            job, SocialState.PENDING_REVIEW, "n8n_proposal_received", "n8n"
        )
        return job

    def approve(
        self, job_id: str, *, approval_id: str, approved_by: str, content_version: int
    ) -> SocialJob:
        job = self._get(job_id)
        if (
            job.state != SocialState.PENDING_REVIEW
            or content_version != job.content_version
        ):
            raise SocialError(
                "APPROVAL_STATE_CONFLICT",
                "approval does not bind current review version",
            )
        job.approval = Approval(approval_id, approved_by, self.now(), content_version)
        self._transition(
            job,
            SocialState.APPROVED,
            "human_approved",
            approved_by,
            approval_id=approval_id,
        )
        return job

    def schedule(self, job_id: str) -> SocialJob:
        job = self._get(job_id)
        claim = self.claim_key(job)
        if claim in self.claims:
            return self.jobs[self.claims[claim]]
        if job.state != SocialState.APPROVED or job.approval is None:
            raise SocialError("APPROVAL_REQUIRED", "immutable approval required")
        if job.scheduled_at <= self.now():
            raise SocialError("SCHEDULE_IN_PAST", "schedule must be in the future", 422)
        self.claims[claim] = job_id
        self._transition(
            job, SocialState.QUEUED, "provider_command_queued", "middleware"
        )
        command = self._command(job, claim)
        try:
            result = self.adapter.schedule(command)
        except SocialError as exc:
            job.attempts += 1
            if exc.code == "POSTLY_TIMEOUT":
                self._transition(
                    job,
                    SocialState.RECONCILIATION_REQUIRED,
                    "provider_write_uncertain",
                    "middleware",
                )
            elif exc.status_code in {429, 502, 503}:
                job.last_error_category = "temporary"
                job.next_attempt_at = self.now() + timedelta(
                    seconds=min(300, 5 * (2 ** (job.attempts - 1)))
                )
                self._transition(
                    job,
                    SocialState.FAILED,
                    "retry_scheduled",
                    "middleware",
                    attempt=job.attempts,
                )
            else:
                self._transition(
                    job, SocialState.FAILED, "provider_failed", "middleware"
                )
            return job
        self._apply_result(job, result)
        return job

    def retry(self, job_id: str) -> SocialJob:
        job = self._get(job_id)
        if job.last_error_category not in self.RETRYABLE or job.attempts >= 3:
            raise SocialError("RETRY_NOT_ALLOWED", "failure is not safely retryable")
        job.state = SocialState.APPROVED
        self.claims.pop(self.claim_key(job), None)
        return self.schedule(job_id)

    def reconcile(self, job_id: str) -> SocialJob:
        job = self._get(job_id)
        if job.state != SocialState.RECONCILIATION_REQUIRED:
            return job
        result = self.adapter.find(self._command(job, self.claim_key(job)))
        if result:
            self._apply_result(job, result, action="provider_readback_reconciled")
        return job

    def analytics(self, job_id: str) -> dict[str, int]:
        job = self._get(job_id)
        if not job.provider_group_id:
            raise SocialError(
                "ANALYTICS_NOT_READY", "provider post has no stable identifier"
            )
        return self.adapter.analytics(job.provider_group_id)

    def _command(self, job: SocialJob, claim: str) -> dict[str, Any]:
        assert job.approval is not None
        return {
            "event_id": str(uuid4()),
            "correlation_id": job.correlation_id,
            "idempotency_key": claim,
            "organization_id": job.organization_id,
            "workspace_id": job.workspace_id,
            "campaign_id": job.campaign_id,
            "content_job_id": job.content_job_id,
            "content_version": job.content_version,
            "approval_id": job.approval.approval_id,
            "approved_by": job.approval.approved_by,
            "approved_at": job.approval.approved_at.isoformat(),
            "integration_ids": list(job.integration_ids),
            "scheduled_at": job.scheduled_at.isoformat(),
            "preferred_language": job.preferred_language,
            "operation": "schedule_post",
            "payload": {"caption": job.caption},
        }

    def _apply_result(
        self, job: SocialJob, result: dict[str, Any], action: str = "provider_scheduled"
    ) -> None:
        job.provider_group_id = result["postly_group_id"]
        job.provider_results = result["provider_results"]
        job.last_error_category = None
        job.next_attempt_at = None
        self._transition(
            job,
            SocialState.SCHEDULED,
            action,
            "mock-postly",
            postly_group_id=job.provider_group_id,
        )

    def _get(self, job_id: str) -> SocialJob:
        try:
            return self.jobs[job_id]
        except KeyError as exc:
            raise SocialError("JOB_NOT_FOUND", "social job not found", 404) from exc


def serialize_job(job: SocialJob) -> dict[str, Any]:
    return {
        "content_job_id": job.content_job_id,
        "content_version": job.content_version,
        "state": job.state,
        "correlation_id": job.correlation_id,
        "postly_group_id": job.provider_group_id,
        "provider_results": job.provider_results,
        "attempts": job.attempts,
        "next_attempt_at": job.next_attempt_at.isoformat()
        if job.next_attempt_at
        else None,
        "audit_count": len(job.audit),
        "mock": True,
    }
