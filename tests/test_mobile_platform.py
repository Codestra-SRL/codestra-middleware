import pytest

from app.core.mobile import MobileSecurityError, safe_push_payload, validate_deep_link


def test_deep_links_are_host_and_token_safe():
    assert validate_deep_link("https://app.codestra.co/leads/123") == "/leads/123"
    with pytest.raises(MobileSecurityError):
        validate_deep_link("https://evil.example/leads/123")
    with pytest.raises(MobileSecurityError):
        validate_deep_link("https://app.codestra.co/leads/123?token=secret")


def test_push_payload_rejects_sensitive_content():
    payload = safe_push_payload("Callback", "A callback is due", "/callbacks/123")
    assert payload["path"] == "/callbacks/123"
    with pytest.raises(MobileSecurityError):
        safe_push_payload("Alert", "password reset token", "/settings")
