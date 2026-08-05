"""Fail-closed commercial subscription, entitlement, and billing contracts."""
from dataclasses import dataclass

ENTITLEMENT_DECISIONS = frozenset({"ALLOWED", "ALLOWED_WITH_LIMIT", "TRIAL", "UPGRADE_REQUIRED", "APPROVAL_REQUIRED", "SUSPENDED", "EXPIRED", "DENIED"})


@dataclass(frozen=True)
class EntitlementRequest:
    tenant_id: str
    workspace_id: str
    feature: str
    current_usage: int
    limit: int
    subscription_active: bool
    suspended: bool = False


def decide_entitlement(request: EntitlementRequest) -> str:
    if not request.tenant_id or not request.workspace_id or not request.feature:
        return "DENIED"
    if request.suspended or not request.subscription_active:
        return "SUSPENDED"
    if request.limit < 0 or request.current_usage < 0:
        return "DENIED"
    if request.current_usage >= request.limit:
        return "UPGRADE_REQUIRED"
    return "ALLOWED_WITH_LIMIT"


def usage_event_is_new(*, existing_key: str | None, event_key: str) -> bool:
    return bool(event_key and existing_key != event_key)


def approve_service_credit(*, human_approved: bool, eligible: bool, ai_requested: bool) -> bool:
    return bool(human_approved and eligible and not ai_requested)


def approve_suspension(*, human_approved: bool, reason: str, scope: str) -> bool:
    return bool(human_approved and reason and scope)
