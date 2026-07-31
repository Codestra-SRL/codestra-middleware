import hashlib
import hmac
from datetime import UTC, datetime

import pytest

from app.core.lead_callback_auth import (
    AUDIENCE,
    IDENTITY,
    CallbackAuthenticationError,
    verify_callback,
)


def headers(body: bytes, secret: bytes = b"synthetic") -> dict[str, str]:
    body_hash = hashlib.sha256(body).hexdigest()
    timestamp = "2026-01-01T00:00:00+00:00"
    nonce = "synthetic-callback-nonce"
    idem = "d" * 64
    material = f"{IDENTITY}\n{AUDIENCE}\n{timestamp}\n{nonce}\nstaging\n{idem}\n{body_hash}".encode()
    return {
        "X-Service-Identity": IDENTITY,
        "X-Service-Audience": AUDIENCE,
        "X-Codestra-Timestamp": timestamp,
        "X-Codestra-Nonce": nonce,
        "X-Codestra-Content-SHA256": body_hash,
        "X-Codestra-Signature": hmac.new(secret, material, hashlib.sha256).hexdigest(),
        "Idempotency-Key": idem,
        "X-Codestra-Environment": "staging",
    }


def test_callback_hmac_and_replay_rejection():
    body = b'{"synthetic":true}'
    used: set[tuple[str, str]] = set()
    verify_callback(
        body=body,
        headers=headers(body),
        secret=b"synthetic",
        environment="staging",
        used_nonces=used,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    with pytest.raises(CallbackAuthenticationError, match="reused"):
        verify_callback(
            body=body,
            headers=headers(body),
            secret=b"synthetic",
            environment="staging",
            used_nonces=used,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_callback_wrong_signature_denied():
    body = b'{"synthetic":true}'
    value = headers(body)
    value["X-Codestra-Signature"] = "0" * 64
    with pytest.raises(CallbackAuthenticationError, match="invalid"):
        verify_callback(
            body=body,
            headers=value,
            secret=b"synthetic",
            environment="staging",
            used_nonces=set(),
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
