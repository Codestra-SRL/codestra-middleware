"""Fail-closed SaaS plan, entitlement, provisioning and quota contracts."""
from dataclasses import dataclass

ACCOUNT_STATES = frozenset({"DRAFT", "PENDING_VERIFICATION", "PENDING_PAYMENT", "PROVISIONING", "TRIAL", "ACTIVE", "PAST_DUE", "SUSPENDED", "CANCELLATION_PENDING", "CANCELLED", "OFFBOARDING", "OFFBOARDED", "PROVISIONING_FAILED"})
PROVISIONING_STATES = frozenset({"REQUESTED", "VALIDATING", "ACCOUNT_CREATING", "TENANT_CREATING", "WORKSPACE_CREATING", "ODOO_CUSTOMER_CREATING", "OWNER_INVITING", "ENTITLEMENTS_APPLYING", "BRANDING_APPLYING", "DOMAIN_PENDING", "INTEGRATIONS_CONFIGURING", "READY_FOR_ACTIVATION", "ACTIVE", "RETRY_SCHEDULED", "FAILED", "ROLLING_BACK", "ROLLED_BACK", "CANCELLED"})


@dataclass(frozen=True)
class PlanContract:
    code: str
    display_name: str
    entitlements: dict[str, int | bool | str]


PLAN_CONTRACTS = (
    PlanContract("STARTER", "Starter Test", {"crm.users.max": 3, "ai.requests.monthly": 100, "portal.enabled": True}),
    PlanContract("GROWTH", "Growth Test", {"crm.users.max": 10, "ai.requests.monthly": 1000, "portal.enabled": True, "bi_dashboard.enabled": True}),
    PlanContract("PROFESSIONAL", "Professional Test", {"crm.users.max": 25, "ai.requests.monthly": 5000, "portal.enabled": True, "agent_assist.enabled": True}),
    PlanContract("ENTERPRISE", "Enterprise Test", {"crm.users.max": 100, "ai.requests.monthly": 25000, "portal.enabled": True, "custom_domain": True}),
)


def quota_outcome(used: int, allowance: int, warning_ratio: float = 0.8) -> str:
    if allowance <= 0 or used >= allowance:
        return "HARD_LIMIT_REACHED"
    if used >= int(allowance * warning_ratio):
        return "WARNING"
    return "ALLOWED"
