"""Telephony usage, entitlement, and SLA evidence contracts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TelephonyUsage:
    tenant_id: str
    workspace_id: str
    usage_type: str
    quantity: int
    unit: str
    idempotency_key: str


def valid_usage(record: TelephonyUsage) -> bool:
    return bool(record.tenant_id and record.workspace_id and record.usage_type and record.unit and record.idempotency_key and record.quantity >= 0)


def entitlement_allows(*, current: int, limit: int, suspended: bool = False) -> str:
    if suspended:
        return "SUSPENDED"
    if current < 0 or limit < 0:
        return "DENIED"
    if current >= limit:
        return "UPGRADE_REQUIRED"
    return "ALLOWED_WITH_LIMIT"
