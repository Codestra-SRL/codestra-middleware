from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

import httpx

from app.integrations.hootsuite.exceptions import HootsuiteError


AUTHORIZE_URL = "https://platform.hootsuite.com/oauth2/auth"
TOKEN_URL = "https://platform.hootsuite.com/oauth2/token"  # nosec B105 -- endpoint


class OAuthStateRepository(Protocol):
    async def persist(
        self,
        *,
        state: str,
        tenant_reference: str,
        nonce: str,
        issued_at: datetime,
        ttl_seconds: int,
    ) -> None: ...

    async def consume(self, *, state: str, tenant_reference: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class OAuthToken:
    access_token: str
    refresh_token: str
    expires_at: int
    scope: str = ""

    @classmethod
    def from_response(
        cls, body: dict[str, object], previous_refresh: str = ""
    ) -> "OAuthToken":
        access = str(body.get("access_token") or "")
        if not access:
            raise HootsuiteError(
                "authentication", "Hootsuite token response is invalid"
            )
        return cls(
            access,
            str(body.get("refresh_token") or previous_refresh),
            int(time.time()) + max(0, int(str(body.get("expires_in") or 0))),
            str(body.get("scope") or ""),
        )


class TokenFileStore:
    """Root-mounted runtime token file. Token values never enter settings or logs."""

    def __init__(self, filename: str) -> None:
        self.path = Path(filename) if filename else None

    def load(self) -> OAuthToken | None:
        if self.path is None or not self.path.is_file():
            return None
        if self.path.stat().st_mode & 0o077:
            raise HootsuiteError(
                "not_configured", "Hootsuite token file permissions are unsafe"
            )
        try:
            body = json.loads(self.path.read_text(encoding="utf-8"))
            return OAuthToken(
                str(body["access_token"]),
                str(body.get("refresh_token") or ""),
                int(body["expires_at"]),
                str(body.get("scope") or ""),
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise HootsuiteError(
                "not_configured", "Hootsuite token file is invalid"
            ) from exc

    def save(self, token: OAuthToken) -> None:
        if self.path is None or not self.path.is_absolute():
            raise HootsuiteError(
                "not_configured", "Hootsuite token file is not configured"
            )
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        payload = {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_at": token.expires_at,
            "scope": token.scope,
        }
        try:
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            temporary.chmod(0o600)
            os.replace(temporary, self.path)
            self.path.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)


class HootsuiteOAuth:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        state_secret: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.state_secret = state_secret
        self.transport = transport

    def authorization_url(
        self, tenant_reference: str, scopes: tuple[str, ...] = ("offline",)
    ) -> str:
        state, _, _ = self._new_state(tenant_reference)
        return self._authorization_url(state, scopes)

    def _new_state(self, tenant_reference: str) -> tuple[str, datetime, str]:
        if not all((self.client_id, self.redirect_uri, self.state_secret)):
            raise HootsuiteError("not_configured", "Hootsuite OAuth is not configured")
        if not tenant_reference:
            raise HootsuiteError("authentication", "Hootsuite OAuth state is invalid")
        nonce = secrets.token_urlsafe(24)
        issued_at = datetime.fromtimestamp(time.time(), timezone.utc)
        issued = str(int(issued_at.timestamp()))
        value = f"{tenant_reference}.{issued}.{nonce}"
        signature = hmac.new(
            self.state_secret.encode(), value.encode(), hashlib.sha256
        ).hexdigest()
        return f"{value}.{signature}", issued_at, nonce

    def _authorization_url(self, state: str, scopes: tuple[str, ...]) -> str:
        return f"{AUTHORIZE_URL}?{urlencode({'response_type': 'code', 'client_id': self.client_id, 'redirect_uri': self.redirect_uri, 'scope': ' '.join(scopes), 'state': state})}"

    async def persistent_authorization_url(
        self,
        tenant_reference: str,
        repository: OAuthStateRepository,
        *,
        scopes: tuple[str, ...] = ("offline",),
        ttl_seconds: int = 600,
    ) -> str:
        if ttl_seconds <= 0:
            raise HootsuiteError("authentication", "Hootsuite OAuth state is invalid")
        state, issued_at, nonce = self._new_state(tenant_reference)
        await repository.persist(
            state=state,
            tenant_reference=tenant_reference,
            nonce=nonce,
            issued_at=issued_at,
            ttl_seconds=ttl_seconds,
        )
        return self._authorization_url(state, scopes)

    async def verify_persistent_state(
        self,
        state: str,
        repository: OAuthStateRepository,
        *,
        max_age_seconds: int = 600,
    ) -> str:
        tenant = self._verify_signature(state, max_age_seconds=max_age_seconds)
        if not await repository.consume(state=state, tenant_reference=tenant):
            raise HootsuiteError("authentication", "Hootsuite OAuth state is invalid")
        return tenant

    def _verify_signature(self, state: str, *, max_age_seconds: int) -> str:
        try:
            tenant, issued, nonce, supplied = state.rsplit(".", 3)
            value = f"{tenant}.{issued}.{nonce}"
            expected = hmac.new(
                self.state_secret.encode(), value.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, supplied):
                raise ValueError
            age = int(time.time()) - int(issued)
            if age < 0 or age > max_age_seconds:
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise HootsuiteError(
                "authentication", "Hootsuite OAuth state is invalid"
            ) from exc
        return tenant

    async def _token(
        self, data: dict[str, str], previous_refresh: str = ""
    ) -> OAuthToken:
        try:
            async with httpx.AsyncClient(
                timeout=15, transport=self.transport
            ) as client:
                response = await client.post(
                    TOKEN_URL, data=data, auth=(self.client_id, self.client_secret)
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise HootsuiteError(
                "temporary", "Hootsuite OAuth is unavailable", retryable=True
            ) from exc
        if response.status_code in (400, 401):
            raise HootsuiteError(
                "authentication",
                "Hootsuite OAuth rejected the request",
                status=response.status_code,
            )
        if response.status_code >= 500:
            raise HootsuiteError(
                "temporary",
                "Hootsuite OAuth is unavailable",
                retryable=True,
                status=response.status_code,
            )
        try:
            return OAuthToken.from_response(response.json(), previous_refresh)
        except ValueError as exc:
            raise HootsuiteError(
                "authentication", "Hootsuite token response is invalid"
            ) from exc

    async def exchange_code(self, code: str) -> OAuthToken:
        return await self._token(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
            }
        )

    async def refresh(self, refresh_token: str) -> OAuthToken:
        if not refresh_token:
            raise HootsuiteError(
                "authentication", "Hootsuite reauthorization is required"
            )
        return await self._token(
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            refresh_token,
        )
