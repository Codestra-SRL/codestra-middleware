import pytest

from app.core.auth import (
    BearerAuthError,
    authenticated_service_subject,
    verify_bearer,
)


def test_application_imports_with_readiness_response_types():
    from app.main import app

    assert app.title == "Codestra Middleware"


def test_bearer_validation_accepts_only_exact_secret():
    verify_bearer("Bearer expected", "expected")
    with pytest.raises(BearerAuthError, match="invalid bearer"):
        verify_bearer("Bearer wrong", "expected")
    with pytest.raises(BearerAuthError, match="missing or invalid"):
        verify_bearer("", "expected")


def test_bearer_validation_fails_closed_without_configuration():
    with pytest.raises(BearerAuthError, match="unavailable"):
        verify_bearer("Bearer anything", "")


def test_authenticated_service_subject_is_derived_from_verified_credential():
    first = authenticated_service_subject("Bearer expected", "expected")
    second = authenticated_service_subject("Bearer expected", "expected")
    assert first == second
    assert first.startswith("service:middleware:")
    assert "expected" not in first
    with pytest.raises(BearerAuthError, match="invalid bearer"):
        authenticated_service_subject("Bearer attacker", "expected")
