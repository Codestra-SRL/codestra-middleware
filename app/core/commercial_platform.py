"""Commercial provisioning and metering contracts."""

from dataclasses import dataclass

SUBSCRIPTION_STATES = frozenset({"DRAFT", "QUOTE_PENDING", "CONTRACT_PENDING", "READY_FOR_PROVISIONING", "PROVISIONING", "TRIAL", "ACTIVE_STAGING", "ACTIVE_LIMITED_PRODUCTION", "PAUSED", "SUSPENDED", "CANCELLED", "OFFBOARDING", "CLOSED", "RECONCILIATION_REQUIRED"})


@dataclass(frozen=True)
class ProvisioningRequest:
    tenant_id: str
    workspace_id: str
    subscription_id: str
    idempotency_key: str


def provisioning_key(request: ProvisioningRequest) -> str:
    return f"{request.tenant_id}:{request.workspace_id}:{request.subscription_id}:{request.idempotency_key}"


def provisioning_is_new(*, existing_key: str | None, request: ProvisioningRequest) -> bool:
    return bool(request.tenant_id and request.workspace_id and request.subscription_id and request.idempotency_key and existing_key != provisioning_key(request))


def entitlement_decision(*, active: bool, current: int, limit: int, suspended: bool = False) -> str:
    if suspended or not active:
        return "SUSPENDED"
    if current < 0 or limit < 0:
        return "DENIED"
    if current >= limit:
        return "UPGRADE_REQUIRED"
    return "ALLOWED_WITH_LIMIT"
