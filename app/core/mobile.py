"""Fail-closed mobile device, deep-link and notification contracts."""
from dataclasses import dataclass
from urllib.parse import urlparse

DEVICE_STATES = frozenset({"PENDING", "TRUSTED", "UNTRUSTED", "REVOKED", "BLOCKED", "EXPIRED"})
ROLES = frozenset({"CUSTOMER_OWNER", "CUSTOMER_MANAGER", "CUSTOMER_ANALYST", "SALES_AGENT", "CALL_CENTER_AGENT", "SUPERVISOR", "MANAGER", "EXECUTIVE", "FIELD_EMPLOYEE", "ADMINISTRATOR"})


class MobileSecurityError(ValueError):
    pass


def validate_device_state(state: str) -> str:
    if state not in DEVICE_STATES:
        raise MobileSecurityError("invalid device state")
    return state


def validate_deep_link(url: str, allowed_hosts: frozenset[str] = frozenset({"app.codestra.co"})) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "codestra"} or parsed.netloc not in allowed_hosts or "token" in parsed.query.lower():
        raise MobileSecurityError("unsafe deep link")
    return parsed.path


def safe_push_payload(title: str, body: str, path: str) -> dict[str, str]:
    if any(value.lower().find(secret) >= 0 for value in (title, body, path) for secret in ("password", "token", "secret", "card")):
        raise MobileSecurityError("sensitive push payload")
    return {"title": title[:120], "body": body[:240], "path": validate_deep_link("https://app.codestra.co" + path)}


@dataclass(frozen=True)
class SyncOperation:
    operation_id: str
    tenant_id: str
    resource: str
    version: int
