"""Fail-closed contracts for named-tenant AI Workforce pilots."""
from dataclasses import dataclass

AUTONOMY_LEVELS = frozenset({"LEVEL_0_DISABLED", "LEVEL_1_OBSERVE_ONLY", "LEVEL_2_DRAFT_ONLY", "LEVEL_3_APPROVAL_REQUIRED", "LEVEL_4_LIMITED_AUTONOMY", "LEVEL_5_PROHIBITED_DURING_PILOT"})
PILOT_STATES = frozenset({"PROPOSED", "VALIDATING", "SECURITY_REVIEW", "BUSINESS_REVIEW", "READY_FOR_APPROVAL", "APPROVED", "CONFIGURING", "INTERNAL_TEST", "PILOT_ACTIVE", "PAUSED", "SUSPENDED", "EXIT_REVIEW", "COMPLETED", "REJECTED"})
ALLOWLIST = frozenset({"crm.lead.read", "support.ticket.read", "knowledge.search", "summary.create", "email.draft", "support.reply.draft", "crm.activity.draft", "report.draft", "calendar.propose", "internal.task.create", "n8n.readonly.execute", "callback.staging.create"})


@dataclass(frozen=True)
class PilotAdmission:
    pilot_id: str
    tenant_id: str
    workspace_id: str
    employee_id: str
    autonomy_level: str
    human_owner_id: str
    action: str
    readiness_passed: bool
    budget_available: bool
    suspended: bool = False


def authorize_admission(admission: PilotAdmission) -> tuple[bool, str]:
    if not all((admission.pilot_id, admission.tenant_id, admission.workspace_id, admission.employee_id, admission.human_owner_id)):
        return False, "MISSING_CONTEXT"
    if admission.autonomy_level not in AUTONOMY_LEVELS:
        return False, "INVALID_AUTONOMY_LEVEL"
    if admission.action not in ALLOWLIST:
        return False, "ACTION_NOT_ALLOWLISTED"
    if admission.suspended:
        return False, "PILOT_SUSPENDED"
    if not admission.readiness_passed:
        return False, "READINESS_GATE_FAILED"
    if not admission.budget_available:
        return False, "BUDGET_EXCEEDED"
    if admission.autonomy_level in {"LEVEL_0_DISABLED", "LEVEL_5_PROHIBITED_DURING_PILOT"}:
        return False, "AUTONOMY_DISABLED"
    return True, "VALID"


def pilot_limits_ok(*, tenant_count: int, workspace_count: int, employee_count: int, level4_count: int) -> bool:
    return bool(tenant_count <= 3 and workspace_count <= 6 and employee_count <= 8 and level4_count <= 2)


def emergency_suspend(*, operator_id: str, mfa_verified: bool, reason: str) -> bool:
    return bool(operator_id and mfa_verified and reason)
