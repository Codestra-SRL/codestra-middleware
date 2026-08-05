"""Fail-closed Tool Gateway contracts; adapters are never called by this module."""
from dataclasses import dataclass

TOOL_RISK_LEVELS = frozenset({"READ_ONLY", "LOW_RISK_WRITE", "REVERSIBLE_WRITE", "APPROVAL_REQUIRED", "HIGH_RISK", "PROHIBITED"})
REQUEST_STATES = frozenset({"REQUESTED", "VALIDATING", "POLICY_CHECKING", "PERMISSION_DENIED", "APPROVAL_REQUIRED", "WAITING_FOR_APPROVAL", "APPROVED", "QUEUED", "EXECUTING", "SUCCEEDED", "FAILED_RETRYABLE", "RETRY_SCHEDULED", "FAILED_FINAL", "CANCELLED", "ROLLBACK_REQUESTED", "ROLLING_BACK", "ROLLED_BACK", "RECONCILIATION_REQUIRED", "RECONCILED", "SECURITY_BLOCKED"})
PROHIBITED_ACTIONS = frozenset({"trading.live.execute", "transfer.money", "withdraw.funds", "delete.production", "read.secrets", "change.approval.policy", "create.privileged_user", "change.carrier"})
RETRYABLE_ERRORS = frozenset({"TIMEOUT", "TEMPORARY_NETWORK", "PROVIDER_UNAVAILABLE", "RATE_LIMITED", "DATABASE_LOCK"})


@dataclass(frozen=True)
class ToolRequest:
    employee_id: str
    employee_version: str
    task_id: str
    tenant_id: str
    workspace_id: str
    tool_code: str
    tool_version: str
    action: str
    reason: str
    input: dict
    idempotency_key: str
    trace_id: str
    permission_granted: bool = False
    approval_required: bool = False
    approved: bool = False
    risk_level: str = "READ_ONLY"


def validate_request(request: ToolRequest) -> tuple[bool, str]:
    required = (request.employee_id, request.employee_version, request.task_id, request.tenant_id, request.workspace_id, request.tool_code, request.tool_version, request.action, request.reason, request.idempotency_key, request.trace_id)
    if not all(required):
        return False, "MISSING_CONTEXT"
    if request.risk_level not in TOOL_RISK_LEVELS:
        return False, "INVALID_RISK_LEVEL"
    if request.action in PROHIBITED_ACTIONS or request.risk_level == "PROHIBITED":
        return False, "PROHIBITED_ACTION"
    if not request.permission_granted:
        return False, "PERMISSION_DENIED"
    if request.approval_required and not request.approved:
        return False, "APPROVAL_REQUIRED"
    return True, "VALID"


def classify_error(error_code: str) -> str:
    return "RETRYABLE" if error_code in RETRYABLE_ERRORS else "FINAL"


def retry_allowed(error_code: str, attempt: int, maximum_retries: int) -> bool:
    return classify_error(error_code) == "RETRYABLE" and 0 <= attempt < maximum_retries


def idempotency_replay(*, existing_key: str | None, request_key: str) -> bool:
    return bool(existing_key and request_key and existing_key == request_key)


def same_scope(*, tenant_id: str, workspace_id: str, record_tenant_id: str, record_workspace_id: str) -> bool:
    return bool(tenant_id and workspace_id and tenant_id == record_tenant_id and workspace_id == record_workspace_id)
