"""Fail-closed customer portal authorization helpers."""
from fastapi import Header, HTTPException

CUSTOMER_ROLES = frozenset({
    "CUSTOMER_OWNER", "CUSTOMER_ADMIN", "CUSTOMER_MANAGER", "CUSTOMER_FINANCE",
    "CUSTOMER_SUPPORT", "CUSTOMER_ANALYST", "CUSTOMER_READ_ONLY", "CUSTOMER_API_USER",
})


def require_customer_scope(tenant_id: str = Header("", alias="X-Customer-Tenant-ID"), role: str = Header("", alias="X-Customer-Role")) -> tuple[str, str]:
    if not tenant_id or role not in CUSTOMER_ROLES:
        raise HTTPException(403, "customer portal authorization required")
    return tenant_id, role


def require_customer_feature(enabled: bool) -> None:
    if not enabled:
        raise HTTPException(404, "customer portal unavailable")
