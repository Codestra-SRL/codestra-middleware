"""Fail-closed contracts for AI department orchestration."""
from dataclasses import dataclass

DEPARTMENT_STATES = frozenset({"DRAFT", "CONFIGURING", "READY_FOR_REVIEW", "STAGING_ACTIVE", "PAUSED", "DEGRADED", "SUSPENDED", "RETIRED", "ERROR"})
HANDOFF_STATES = frozenset({"DRAFT", "VALIDATING", "WAITING_FOR_ACCEPTANCE", "ACCEPTED", "REJECTED", "IN_PROGRESS", "COMPLETED", "FAILED", "ESCALATED", "CANCELLED"})


@dataclass(frozen=True)
class DelegationRequest:
    source_employee: str
    target_employee: str
    source_tenant: str
    target_tenant: str
    source_workspace: str
    target_workspace: str
    depth: int
    participant_count: int
    completion_criteria: str
    target_suspended: bool = False
    self_approval: bool = False


def authorize_delegation(request: DelegationRequest) -> tuple[bool, str]:
    if not request.source_employee or not request.target_employee or not request.completion_criteria:
        return False, "MISSING_CONTEXT"
    if request.source_employee == request.target_employee:
        return False, "SELF_DELEGATION"
    if request.source_tenant != request.target_tenant or request.source_workspace != request.target_workspace:
        return False, "SCOPE_MISMATCH"
    if request.depth > 3 or request.participant_count > 8:
        return False, "LIMIT_EXCEEDED"
    if request.target_suspended:
        return False, "TARGET_SUSPENDED"
    if request.self_approval:
        return False, "SELF_APPROVAL"
    return True, "VALID"


def authorize_collaboration(*, tenant_id: str, workspace_id: str, owning_tenant_id: str, owning_workspace_id: str, participant_count: int, budget_remaining: bool) -> bool:
    return bool(tenant_id and workspace_id and tenant_id == owning_tenant_id and workspace_id == owning_workspace_id and 0 < participant_count <= 8 and budget_remaining)


def cross_department_allowed(*, source_department: str, target_department: str, approved: bool, same_tenant: bool) -> bool:
    return bool(source_department and target_department and approved and same_tenant)
