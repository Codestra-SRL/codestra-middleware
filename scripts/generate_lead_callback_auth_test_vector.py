"""Emit the synthetic n8n callback HMAC vector used by source-only tests."""

from __future__ import annotations

import hashlib
import json

from app.core.lead_callback_auth import (
    CALLBACK_METHOD,
    CALLBACK_PATH,
    canonical_callback_material,
    sign_callback,
)

BODY = b'{"environment":"staging","synthetic":true}'
SECRET = b"synthetic-callback-test-secret"
TIMESTAMP = "2026-01-01T00:00:00+00:00"
NONCE = "synthetic-callback-nonce"
IDEMPOTENCY_KEY = "d" * 64


def build_vector() -> dict[str, str]:
    body_hash = hashlib.sha256(BODY).hexdigest()
    headers = sign_callback(
        body=BODY,
        secret=SECRET,
        timestamp=TIMESTAMP,
        nonce=NONCE,
        idempotency_key=IDEMPOTENCY_KEY,
        environment="staging",
    )
    material = canonical_callback_material(
        method=CALLBACK_METHOD,
        path=CALLBACK_PATH,
        timestamp=TIMESTAMP,
        nonce=NONCE,
        idempotency_key=IDEMPOTENCY_KEY,
        body_sha256=body_hash,
    )
    return {
        "method": CALLBACK_METHOD,
        "path": CALLBACK_PATH,
        "timestamp": TIMESTAMP,
        "nonce": NONCE,
        "idempotency_key": IDEMPOTENCY_KEY,
        "body": BODY.decode("ascii"),
        "body_sha256": body_hash,
        "canonical_material": material.decode("ascii"),
        "expected_signature": headers["X-Codestra-Signature"],
        "secret_classification": "synthetic-test-only",
    }


if __name__ == "__main__":
    print(json.dumps(build_vector(), indent=2, sort_keys=True))
