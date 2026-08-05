"""Fail-closed workflow, outbox, retry, and callback contracts."""

from dataclasses import dataclass

WORKFLOW_STATES = frozenset({"RECEIVED", "VALIDATING", "AUTHORIZING", "WAITING_FOR_APPROVAL", "APPROVED", "OUTBOX_PENDING", "QUEUED", "DISPATCHED", "EXECUTING", "SUCCEEDED", "FAILED_RETRYABLE", "RETRY_SCHEDULED", "FAILED_FINAL", "CANCELLED", "SECURITY_BLOCKED", "RECONCILIATION_REQUIRED", "RECONCILED"})
RESULT_STATES = frozenset({"SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "CANCELLED", "SECURITY_BLOCKED", "APPROVAL_REQUIRED", "EXPIRED", "RECONCILIATION_REQUIRED"})


@dataclass(frozen=True)
class WorkflowContext:
    workflow_code: str
    workflow_version: str
    tenant_id: str
    workspace_id: str
    command_id: str
    correlation_id: str
    trace_id: str
    idempotency_key: str


def valid_workflow_context(context: WorkflowContext) -> bool:
    return all((context.workflow_code, context.workflow_version, context.tenant_id, context.workspace_id, context.command_id, context.correlation_id, context.trace_id, context.idempotency_key))


def valid_transition(previous: str, current: str) -> bool:
    return previous in WORKFLOW_STATES and current in WORKFLOW_STATES and previous != current


def retryable_failure(error_class: str, attempt: int, maximum: int) -> bool:
    return error_class in {"TRANSIENT_NETWORK", "PROVIDER_RATE_LIMIT", "PROVIDER_UNAVAILABLE", "TEMPORARY_DATABASE", "TIMEOUT", "AUTHENTICATION_EXPIRED"} and attempt < maximum


def callback_allowed(*, known_workflow: bool, known_execution: bool, tenant_match: bool, workspace_match: bool, signature_valid: bool, replay: bool, result_state: str) -> tuple[bool, str]:
    if not known_workflow or not known_execution or not tenant_match or not workspace_match:
        return False, "UNKNOWN_OR_MISMATCHED_CONTEXT"
    if not signature_valid:
        return False, "INVALID_SIGNATURE"
    if replay:
        return False, "REPLAY_REJECTED"
    if result_state not in RESULT_STATES:
        return False, "UNKNOWN_RESULT_STATE"
    return True, "VALID"
