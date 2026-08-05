from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import identity
from app.core.identity_provider import IdentityProviderError, KeycloakLifecycleClient, read_protected_secret
from app.main import app


def test_secret_reader_rejects_group_or_world_access(tmp_path: Path):
    secret = tmp_path / "credential"
    secret.write_text("synthetic-value")
    secret.chmod(0o640)
    with pytest.raises(IdentityProviderError):
        read_protected_secret(str(secret))
    secret.chmod(0o600)
    assert read_protected_secret(str(secret)) == "synthetic-value"


def test_provider_requires_https():
    with pytest.raises(IdentityProviderError):
        KeycloakLifecycleClient(
            token_url="http://identity/token",
            logout_url="https://identity/logout",
            admin_base_url="https://identity/admin",
            browser_client_id="browser",
            browser_client_secret_file="/run/secrets/browser",
            admin_client_id="admin",
            admin_client_secret_file="/run/secrets/admin",
        )


def test_login_failure_is_redacted(monkeypatch):
    class Provider:
        async def login(self, username, password, otp):
            assert password == "synthetic-password"
            raise IdentityProviderError("upstream included a credential")

    monkeypatch.setattr(identity, "_provider", lambda: Provider())
    response = TestClient(app).post(
        "/api/v1/auth/login",
        json={"username": "synthetic-user", "password": "synthetic-password"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "authentication failed"}
    assert "synthetic-password" not in response.text
    assert "upstream" not in response.text


def test_mfa_requires_otp_before_provider_call(monkeypatch):
    monkeypatch.setattr(identity, "_provider", lambda: pytest.fail("provider called"))
    response = TestClient(app).post(
        "/api/v1/auth/mfa",
        json={"username": "synthetic-user", "password": "synthetic-password"},
    )
    assert response.status_code == 422


def test_service_accounts_are_created_disabled(monkeypatch):
    class Provider:
        async def admin_request(self, method, path, *, payload=None):
            assert method == "POST"
            assert path == "/clients"
            assert payload["enabled"] is False
            assert payload["directAccessGrantsEnabled"] is False

    class Admin:
        def require_permission(self, permission):
            assert permission == "identity.write"

    monkeypatch.setattr(identity, "_provider", lambda: Provider())
    monkeypatch.setattr(identity, "_admin", lambda authorization, permission: Admin())
    response = TestClient(app).post(
        "/api/v1/service-accounts",
        headers={"Authorization": "Bearer synthetic"},
        json={"client_id": "synthetic-service", "display_name": "Synthetic", "scopes": ["crm.read"]},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "DISABLED_PENDING_SCOPE_APPROVAL"


def test_federation_provider_is_disabled_pending_review(monkeypatch):
    captured = {}

    class Provider:
        async def admin_request(self, method, path, *, payload=None):
            captured.update(payload)

    monkeypatch.setattr(identity, "_provider", lambda: Provider())
    monkeypatch.setattr(identity, "_admin", lambda authorization, permission: object())
    response = TestClient(app).post(
        "/api/v1/identity-providers",
        headers={"Authorization": "Bearer synthetic"},
        json={"alias": "synthetic-oidc", "provider": "oidc", "enabled": True, "metadata_url": "https://idp.invalid/config"},
    )
    assert response.status_code == 201
    assert captured["enabled"] is False
    assert captured["trustEmail"] is False
