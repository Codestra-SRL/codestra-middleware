"""Provider-neutral integration contracts with replay and SSRF-safe defaults."""

import hashlib
import hmac
import time
from dataclasses import dataclass

INTEGRATION_STATES = frozenset({"REQUESTED", "VALIDATING", "AUTHORIZING", "WAITING_FOR_APPROVAL", "APPROVED", "QUEUED", "EXECUTING", "SUCCEEDED", "FAILED_RETRYABLE", "RETRY_SCHEDULED", "FAILED_FINAL", "CANCELLED", "SECURITY_BLOCKED", "RECONCILIATION_REQUIRED", "RECONCILED"})


@dataclass(frozen=True)
class ConnectorCapability:
    connector_code: str
    capability: str
    risk_level: str
    approval_required: bool
    idempotency_required: bool = True


def authorize_capability(*, tenant_id: str, workspace_id: str, permission_granted: bool, approval_granted: bool, production_enabled: bool) -> tuple[bool, str]:
    if not tenant_id or not workspace_id:
        return False, "MISSING_SCOPE"
    if not permission_granted:
        return False, "PERMISSION_DENIED"
    if not approval_granted:
        return False, "APPROVAL_REQUIRED"
    if not production_enabled:
        return False, "PRODUCTION_CONNECTORS_DISABLED"
    return True, "VALID"


def verify_webhook(*, body: bytes, signature: str, secret: bytes, timestamp: int, now: int | None = None, ttl_seconds: int = 300) -> tuple[bool, str]:
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > ttl_seconds:
        return False, "EXPIRED_TIMESTAMP"
    expected = hmac.new(secret, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False, "INVALID_SIGNATURE"
    return True, "VALID"


def retryable_error(*, status_code: int, attempt: int, max_attempts: int) -> bool:
    return status_code in {408, 429, 500, 502, 503, 504} and attempt < max_attempts


def safe_provider_url(url: str) -> bool:
    return url.startswith("https://") and not any(token in url.lower() for token in ("127.0.0.1", "localhost", "169.254.169.254", "file:"))
