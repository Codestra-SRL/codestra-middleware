"""Fail-closed contracts for the Codestra AI Business Operating System."""
from dataclasses import dataclass

GRAPH_TYPES = frozenset({"CUSTOMER", "COMPANY", "EMPLOYEE", "AI_EMPLOYEE", "PROJECT", "TASK", "CALL", "MEETING", "INVOICE", "PAYMENT", "TICKET", "CONTRACT", "EMAIL", "DOCUMENT", "PRODUCT", "CAMPAIGN", "WORKFLOW", "KNOWLEDGE", "GOAL", "DEPARTMENT"})
COMMAND_ACTIONS = frozenset({"FIND", "SCHEDULE", "SHOW", "CREATE_DRAFT", "PROPOSE", "SUMMARIZE", "OPEN_INCIDENT"})


@dataclass(frozen=True)
class CommandRequest:
    tenant_id: str
    workspace_id: str
    actor_id: str
    action: str
    query: str
    idempotency_key: str
    approved: bool = False


def validate_command(request: CommandRequest) -> tuple[bool, str]:
    if not all((request.tenant_id, request.workspace_id, request.actor_id, request.action, request.query, request.idempotency_key)):
        return False, "MISSING_CONTEXT"
    if request.action not in COMMAND_ACTIONS:
        return False, "ACTION_NOT_ALLOWLISTED"
    if request.action in {"CREATE_DRAFT", "PROPOSE", "OPEN_INCIDENT"} and not request.approved:
        return False, "APPROVAL_REQUIRED"
    return True, "VALID"


def graph_edge_allowed(*, source_tenant: str, target_tenant: str, source_workspace: str, target_workspace: str) -> bool:
    return bool(source_tenant and source_workspace and source_tenant == target_tenant and source_workspace == target_workspace)


def universal_result_allowed(*, tenant_id: str, workspace_id: str, result_tenant: str, result_workspace: str) -> bool:
    return graph_edge_allowed(source_tenant=tenant_id, target_tenant=result_tenant, source_workspace=workspace_id, target_workspace=result_workspace)
