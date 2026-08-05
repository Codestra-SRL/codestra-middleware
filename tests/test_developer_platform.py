import pytest
from fastapi import HTTPException

from app.core.developer_platform import DeveloperPlatformError, sign_webhook, validate_scopes, verify_webhook
from app.api.v1.developer import require_developer


def test_scopes_are_allowlisted():
    assert validate_scopes(["leads.read", "leads.read"]) == ("leads.read",)
    with pytest.raises(DeveloperPlatformError):
        validate_scopes(["admin.root"])


def test_webhook_signature_has_timestamp_replay_protection():
    payload = b'{"event":"lead.created"}'
    signature = sign_webhook("test-secret", "1700000000", payload)
    assert verify_webhook("test-secret", "1700000000", payload, signature, now=1700000000)
    assert not verify_webhook("test-secret", "1700000000", payload, signature, now=1700001000)


def test_developer_role_guard_rejects_read_only_customer():
    with pytest.raises(HTTPException) as exc:
        require_developer("CUSTOMER_READ_ONLY")
    assert exc.value.status_code == 403
