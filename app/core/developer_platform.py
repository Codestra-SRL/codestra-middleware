"""Public Developer Platform contracts; production access is fail-closed."""
import hashlib
import hmac
import secrets
import time

PUBLIC_SCOPES = frozenset({"organizations.read", "leads.read", "calls.read", "tickets.read", "projects.read", "billing.read", "ai.request", "webhooks.manage"})
WEBHOOK_EVENTS = frozenset({"lead.created", "lead.updated", "lead.approved", "call.completed", "transcript.ready", "qa.completed", "ticket.created", "ticket.updated", "invoice.created", "invoice.paid", "project.updated", "plugin.installed", "subscription.updated"})


class DeveloperPlatformError(ValueError):
    pass


def validate_scopes(scopes: list[str]) -> tuple[str, ...]:
    values = tuple(dict.fromkeys(scopes))
    if not values or any(scope not in PUBLIC_SCOPES for scope in values):
        raise DeveloperPlatformError("invalid or unauthorized scope")
    return values


def create_api_key() -> tuple[str, str]:
    raw = "cs_live_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def sign_webhook(secret: str, timestamp: str, payload: bytes) -> str:
    if not secret or not timestamp:
        raise DeveloperPlatformError("webhook signing inputs required")
    return hmac.new(secret.encode(), timestamp.encode() + b"." + payload, hashlib.sha256).hexdigest()


def verify_webhook(secret: str, timestamp: str, payload: bytes, signature: str, *, now: int | None = None, tolerance: int = 300) -> bool:
    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = int(time.time()) if now is None else now
    return abs(current - timestamp_int) <= tolerance and hmac.compare_digest(sign_webhook(secret, timestamp, payload), signature)
