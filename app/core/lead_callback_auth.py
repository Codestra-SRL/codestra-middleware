from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone


IDENTITY = "codestra-n8n-lead-automation"
AUDIENCE = "codestra-middleware-lead-automation"


class CallbackAuthenticationError(PermissionError):
    pass


def verify_callback(
    *,
    body: bytes,
    headers: dict[str, str],
    secret: bytes,
    environment: str,
    used_nonces: set[tuple[str, str]],
    now: datetime | None = None,
) -> None:
    required = (
        "X-Service-Identity",
        "X-Service-Audience",
        "X-Codestra-Timestamp",
        "X-Codestra-Nonce",
        "X-Codestra-Content-SHA256",
        "X-Codestra-Signature",
        "Idempotency-Key",
        "X-Codestra-Environment",
    )
    if any(not headers.get(name) for name in required):
        raise CallbackAuthenticationError("missing callback signature")
    if (
        headers["X-Service-Identity"] != IDENTITY
        or headers["X-Service-Audience"] != AUDIENCE
    ):
        raise CallbackAuthenticationError("callback identity binding mismatch")
    if headers["X-Codestra-Environment"] != environment:
        raise CallbackAuthenticationError("callback environment mismatch")
    body_hash = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(body_hash, headers["X-Codestra-Content-SHA256"]):
        raise CallbackAuthenticationError("callback body hash mismatch")
    try:
        occurred = datetime.fromisoformat(
            headers["X-Codestra-Timestamp"].replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise CallbackAuthenticationError("invalid callback timestamp") from exc
    now = now or datetime.now(timezone.utc)
    if (
        occurred.tzinfo is None
        or abs((now - occurred.astimezone(timezone.utc)).total_seconds()) > 300
    ):
        raise CallbackAuthenticationError("expired callback timestamp")
    nonce_key = (environment, headers["X-Codestra-Nonce"])
    if nonce_key in used_nonces:
        raise CallbackAuthenticationError("reused callback nonce")
    material = "\n".join(
        (
            IDENTITY,
            AUDIENCE,
            headers["X-Codestra-Timestamp"],
            headers["X-Codestra-Nonce"],
            environment,
            headers["Idempotency-Key"],
            body_hash,
        )
    ).encode()
    expected = hmac.new(secret, material, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, headers["X-Codestra-Signature"]):
        raise CallbackAuthenticationError("invalid callback signature")
    used_nonces.add(nonce_key)
