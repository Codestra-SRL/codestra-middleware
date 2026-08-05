"""Minimal, fail-closed Keycloak lifecycle client.

Credential values are read only from protected files and are never included in
exceptions or return values.
"""

import stat
from pathlib import Path
from typing import Any

import httpx


class IdentityProviderError(RuntimeError):
    pass


def read_protected_secret(filename: str) -> str:
    path = Path(filename)
    if not filename or not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise IdentityProviderError("identity provider credential unavailable")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise IdentityProviderError("identity provider credential permissions unsafe")
    value = path.read_text().strip()
    if not value:
        raise IdentityProviderError("identity provider credential empty")
    return value


class KeycloakLifecycleClient:
    def __init__(
        self,
        *,
        token_url: str,
        logout_url: str,
        admin_base_url: str,
        browser_client_id: str,
        browser_client_secret_file: str,
        admin_client_id: str,
        admin_client_secret_file: str,
        timeout_seconds: float = 10.0,
    ) -> None:
        urls = (token_url, logout_url, admin_base_url)
        if any(not value.startswith("https://") for value in urls):
            raise IdentityProviderError("identity provider HTTPS endpoints required")
        self.token_url = token_url
        self.logout_url = logout_url
        self.admin_base_url = admin_base_url.rstrip("/")
        self.browser_client_id = browser_client_id
        self.browser_client_secret_file = browser_client_secret_file
        self.admin_client_id = admin_client_id
        self.admin_client_secret_file = admin_client_secret_file
        self.timeout_seconds = timeout_seconds

    async def _form(self, url: str, form: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, data=form, headers={"Accept": "application/json"})
        if response.status_code >= 400:
            raise IdentityProviderError("identity provider rejected request")
        result = response.json()
        if not isinstance(result, dict):
            raise IdentityProviderError("identity provider response invalid")
        return result

    async def login(self, username: str, password: str, otp: str | None = None) -> dict[str, Any]:
        form = {
            "grant_type": "password",
            "client_id": self.browser_client_id,
            "client_secret": read_protected_secret(self.browser_client_secret_file),
            "username": username,
            "password": password,
            "scope": "openid",
        }
        if otp:
            form["totp"] = otp
        return await self._form(self.token_url, form)

    async def refresh(self, refresh_token: str) -> dict[str, Any]:
        return await self._form(
            self.token_url,
            {
                "grant_type": "refresh_token",
                "client_id": self.browser_client_id,
                "client_secret": read_protected_secret(self.browser_client_secret_file),
                "refresh_token": refresh_token,
            },
        )

    async def logout(self, refresh_token: str) -> None:
        await self._form(
            self.logout_url,
            {
                "client_id": self.browser_client_id,
                "client_secret": read_protected_secret(self.browser_client_secret_file),
                "refresh_token": refresh_token,
            },
        )

    async def _admin_token(self) -> str:
        response = await self._form(
            self.token_url,
            {
                "grant_type": "client_credentials",
                "client_id": self.admin_client_id,
                "client_secret": read_protected_secret(self.admin_client_secret_file),
            },
        )
        token = response.get("access_token")
        if not isinstance(token, str) or not token:
            raise IdentityProviderError("identity provider admin token unavailable")
        return token

    async def admin_request(
        self, method: str, path: str, *, payload: dict[str, Any] | None = None
    ) -> Any:
        if method not in {"GET", "POST", "PUT", "DELETE"} or not path.startswith("/") or ".." in path:
            raise IdentityProviderError("identity provider admin request invalid")
        token = await self._admin_token()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.request(
                method,
                f"{self.admin_base_url}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        if response.status_code >= 400:
            raise IdentityProviderError("identity provider admin request rejected")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()
