"""Fail-closed AI workforce dispatch and emergency-control contracts."""

from dataclasses import dataclass

GOAL_STATES = frozenset({"DRAFT", "ACTIVE", "PAUSED", "COMPLETED", "CANCELLED", "REVIEW_REQUIRED"})
TASK_STATES = frozenset({"DRAFT", "QUEUED", "WAITING_FOR_APPROVAL", "APPROVED", "RUNNING", "RETRY_SCHEDULED", "COMPLETED", "FAILED", "CANCELLED", "DEAD_LETTER", "RECONCILIATION_REQUIRED"})
EMERGENCY_STATES = frozenset({"CLEAR", "PAUSE_NEW_WORK", "PAUSE_ALL_WORK", "REVOKE_TOOLS", "SHUTDOWN"})


@dataclass(frozen=True)
class DispatchRequest:
    tenant_id: str
    workspace_id: str
    employee_id: str
    department_id: str
    goal_id: str
    task_id: str
    workflow_code: str
    workflow_version: str
    idempotency_key: str
    trace_id: str
    employee_active: bool
    department_active: bool
    goal_active: bool
    permission_granted: bool
    approval_required: bool
    approval_granted: bool
    workflow_approved: bool
    emergency_state: str = "CLEAR"


def authorize_dispatch(request: DispatchRequest) -> tuple[bool, str]:
    """Return a deterministic decision; this function never calls an adapter."""
    required = (request.tenant_id, request.workspace_id, request.employee_id, request.department_id,
                request.goal_id, request.task_id, request.workflow_code, request.workflow_version,
                request.idempotency_key, request.trace_id)
    if not all(required):
        return False, "MISSING_CONTEXT"
    if request.emergency_state not in EMERGENCY_STATES:
        return False, "INVALID_EMERGENCY_STATE"
    if request.emergency_state != "CLEAR":
        return False, "EMERGENCY_CONTROL_ACTIVE"
    if not (request.employee_active and request.department_active and request.goal_active):
        return False, "ACTOR_OR_GOAL_INACTIVE"
    if not request.permission_granted:
        return False, "PERMISSION_DENIED"
    if not request.workflow_approved:
        return False, "WORKFLOW_APPROVAL_REQUIRED"
    if request.approval_required and not request.approval_granted:
        return False, "HUMAN_APPROVAL_REQUIRED"
    return True, "AUTHORIZED"


def initial_task_state(*, approval_required: bool, approval_granted: bool = False) -> str:
    if approval_required and not approval_granted:
        return "WAITING_FOR_APPROVAL"
    return "QUEUED"


def retry_allowed(*, failure_class: str, attempt: int, maximum_attempts: int) -> bool:
    return failure_class in {"TRANSIENT_NETWORK", "PROVIDER_RATE_LIMIT", "PROVIDER_UNAVAILABLE", "TEMPORARY_DATABASE", "TIMEOUT"} and 0 <= attempt < maximum_attempts


def emergency_blocks(state: str) -> bool:
    return state in {"PAUSE_NEW_WORK", "PAUSE_ALL_WORK", "REVOKE_TOOLS", "SHUTDOWN"}

