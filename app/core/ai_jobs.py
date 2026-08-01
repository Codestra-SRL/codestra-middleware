"""Default-off, tenant-scoped AI job and advisory-result control plane."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TenantScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tenant_id: str = Field(min_length=1, max_length=128)
    company_id: int = Field(gt=0)
    business_unit_key: str = Field(min_length=1, max_length=64)
    campaign_key: str = Field(min_length=1, max_length=64)


class AIJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str = Field(min_length=8, max_length=128)
    event_id: str = Field(min_length=8, max_length=128)
    interaction_id: str = Field(min_length=1, max_length=128)
    tenant_scope: TenantScope
    purpose: str
    object_reference: dict[str, str]
    allowed_operations: list[str]
    model_policy: dict[str, Any]
    retention_class: str
    created_at: datetime
    idempotency_key: str = Field(min_length=16, max_length=128)


class AIJobResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    interaction_id: str
    tenant_scope: TenantScope
    model_provider: str
    model_identifier: str
    model_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prompt_version: str
    policy_version: str
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    redaction_status: str
    confidence: float = Field(ge=0, le=1)
    result_payload: dict[str, Any]
    action_proposals: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class AIActionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: str
    job_id: str
    tenant_scope: TenantScope
    decision: str = Field(pattern=r"^(approved|rejected)$")
    approver_id: str
    approver_role: str = Field(pattern=r"^AI (Supervisor Approver|Compliance Reviewer)$")
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decided_at: datetime


@dataclass
class AIJobState:
    request: AIJobRequest
    status: str = "queued"
    result: AIJobResult | None = None
    decisions: list[AIActionDecision] = field(default_factory=list)


class AIJobControl:
    def __init__(self) -> None:
        self.enabled = False
        self.submission_enabled = False
        self.results_enabled = False
        self.decisions_enabled = False
        self.jobs: dict[str, AIJobState] = {}
        self.idempotency: dict[tuple[str, str], str] = {}
        self.outbox: list[dict[str, Any]] = []
        self.quarantine: list[dict[str, str]] = []
        self.audit: list[dict[str, str]] = []

    @staticmethod
    def _scope_key(scope: TenantScope) -> str:
        return json.dumps(scope.model_dump(), sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _hash(value: BaseModel) -> str:
        return hashlib.sha256(value.model_dump_json().encode()).hexdigest()

    def _require(self, switch: bool) -> None:
        if not self.enabled or not switch:
            raise PermissionError("AI control plane is disabled")

    def create(self, request: AIJobRequest) -> AIJobState:
        self._require(self.submission_enabled)
        key = (self._scope_key(request.tenant_scope), request.idempotency_key)
        request_hash = self._hash(request)
        previous = self.idempotency.get(key)
        if previous is not None:
            state = self.jobs[previous]
            if self._hash(state.request) != request_hash:
                raise ValueError("conflicting idempotent replay")
            return state
        if request.model_policy.get("remote_provider_allowed") is not False:
            raise PermissionError("remote provider is default-off")
        state = AIJobState(request)
        self.jobs[request.job_id] = state
        self.idempotency[key] = request.job_id
        self.outbox.append({"event": "ai.job.request.v1", "job_id": request.job_id, "scope": key[0]})
        self.audit.append({"event": "ai.job.created", "job_id": request.job_id, "at": datetime.now(UTC).isoformat()})
        return state

    def get(self, job_id: str, scope: TenantScope) -> AIJobState:
        state = self.jobs.get(job_id)
        if state is None or state.request.tenant_scope != scope:
            raise LookupError("AI job not found")
        return state

    def receive_result(self, result: AIJobResult) -> AIJobState:
        self._require(self.results_enabled)
        state = self.get(result.job_id, result.tenant_scope)
        if state.request.interaction_id != result.interaction_id:
            self.quarantine.append({"job_id": result.job_id, "reason": "interaction mismatch"})
            raise PermissionError("result binding mismatch")
        state.result = result
        state.status = "review_required"
        self.audit.append({"event": "ai.result.accepted", "job_id": result.job_id, "at": datetime.now(UTC).isoformat()})
        return state

    def decide(self, decision: AIActionDecision) -> AIJobState:
        self._require(self.decisions_enabled)
        state = self.get(decision.job_id, decision.tenant_scope)
        if state.result is None:
            raise ValueError("result is not available")
        state.decisions.append(decision)
        self.audit.append({"event": "ai.action.decided", "job_id": decision.job_id, "at": datetime.now(UTC).isoformat()})
        return state

    def reconcile(self) -> int:
        return sum(1 for state in self.jobs.values() if state.status == "queued")
