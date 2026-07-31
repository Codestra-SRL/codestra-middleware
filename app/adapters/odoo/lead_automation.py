from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import uuid4


IDENTITY = "codestra-middleware"
AUDIENCE = "codestra-odoo-lead-automation-api"


def canonical_body(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def signed_headers(
    payload: dict,
    secret: bytes,
    environment: str,
    idempotency_key: str,
    *,
    timestamp: str | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    body_hash = hashlib.sha256(canonical_body(payload)).hexdigest()
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    nonce = nonce or str(uuid4())
    material = "\n".join(
        (IDENTITY, AUDIENCE, timestamp, nonce, environment, idempotency_key, body_hash)
    ).encode()
    signature = hmac.new(secret, material, hashlib.sha256).hexdigest()
    return {
        "X-Service-Identity": IDENTITY,
        "X-Service-Audience": AUDIENCE,
        "X-Codestra-Timestamp": timestamp,
        "X-Codestra-Nonce": nonce,
        "X-Codestra-Content-SHA256": body_hash,
        "X-Codestra-Signature": signature,
        "Idempotency-Key": idempotency_key,
        "X-Codestra-Environment": environment,
    }
