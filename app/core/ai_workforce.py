"""Fail-closed AI employee authorization and collaboration contracts."""
from dataclasses import dataclass

EMPLOYEE_STATUSES = frozenset({"DRAFT", "CONFIGURING", "READY_FOR_REVIEW", "APPROVED", "STAGING_ACTIVE", "PAUSED", "DEGRADED", "SUSPENDED", "REVOKED", "RETIRED", "ERROR"})
TASK_STATES = frozenset({"DRAFT", "QUEUED", "VALIDATING", "WAITING_FOR_APPROVAL", "APPROVED", "RUNNING", "PAUSED", "WAITING_FOR_DEPENDENCY", "COMPLETED", "FAILED", "CANCELLED", "ESCALATED", "RECONCILIATION_REQUIRED"})


@dataclass(frozen=True)
class ToolRequest:
    tenant_id: str
    workspace_id: str
    employee_id: str
    required_permission: str
    granted_permissions: frozenset[str]
    approval_required: bool
    approved: bool
    risk_level: str


@dataclass(frozen=True)
class MemoryRequest:
    tenant_id: str
    workspace_id: str
    memory_tenant_id: str
    memory_workspace_id: str
    authorized: bool


@dataclass(frozen=True)
class Delegation:
    depth: int
    collaborator_count: int
    target_tenant: str
    source_tenant: str


def authorize_tool(request: ToolRequest) -> bool:
    if not request.tenant_id or not request.workspace_id or not request.employee_id:
        return False
    if request.required_permission not in request.granted_permissions:
        return False
    if request.risk_level in {"HIGH_RISK", "PROHIBITED"}:
        return False
    return not request.approval_required or request.approved


def authorize_memory(request: MemoryRequest) -> bool:
    return bool(request.authorized and request.tenant_id and request.workspace_id and request.tenant_id == request.memory_tenant_id and request.workspace_id == request.memory_workspace_id)


def allow_delegation(delegation: Delegation) -> bool:
    return bool(delegation.depth <= 3 and delegation.collaborator_count <= 5 and delegation.source_tenant == delegation.target_tenant)
