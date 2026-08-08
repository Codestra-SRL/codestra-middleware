from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

import httpx

from app.core.config import settings
from app.integrations.hootsuite.exceptions import HootsuiteError
from app.integrations.hootsuite.oauth import HootsuiteOAuth, TokenFileStore


class HootsuiteClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = settings.hootsuite_base_url.rstrip("/")
        self.transport = transport
        self.store = TokenFileStore(settings.hootsuite_token_file)

    async def _access_token(self) -> str:
        token = self.store.load()
        if token is None:
            raise HootsuiteError(
                "not_configured", "Hootsuite authorization is not configured"
            )
        if token.expires_at > int(time.time()) + 60:
            return token.access_token
        oauth = HootsuiteOAuth(
            settings.hootsuite_client_id,
            settings.hootsuite_client_secret,
            settings.hootsuite_redirect_uri,
            settings.hootsuite_oauth_state_secret,
            transport=self.transport,
        )
        refreshed = await oauth.refresh(token.refresh_token)
        self.store.save(refreshed)
        return refreshed.access_token

    async def request(
        self,
        method: str,
        path: str,
        *,
        correlation_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        headers = {
            "Authorization": f"Bearer {await self._access_token()}",
            "Accept": "application/json",
        }
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id
        try:
            async with httpx.AsyncClient(
                timeout=settings.hootsuite_timeout_seconds, transport=self.transport
            ) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}/{path.lstrip('/')}",
                    headers=headers,
                    **kwargs,
                )
        except httpx.ReadTimeout as exc:
            raise HootsuiteError(
                "unknown_result", "Hootsuite result is unknown", unknown_result=True
            ) from exc
        except (httpx.ConnectTimeout, httpx.ConnectError, httpx.NetworkError) as exc:
            raise HootsuiteError(
                "temporary", "Hootsuite connection failed", retryable=True
            ) from exc
        retry_after = response.headers.get("Retry-After")
        if response.status_code == 429:
            raise HootsuiteError(
                "rate_limit",
                "Hootsuite rate limit reached",
                retryable=True,
                status=429,
                retry_after=float(retry_after)
                if retry_after and retry_after.isdigit()
                else None,
            )
        if response.status_code in (401, 403):
            raise HootsuiteError(
                "authentication",
                "Hootsuite authorization failed",
                status=response.status_code,
            )
        if response.status_code == 404:
            raise HootsuiteError(
                "not_found", "Hootsuite resource was not found", status=404
            )
        if response.status_code >= 500:
            raise HootsuiteError(
                "temporary",
                "Hootsuite is unavailable",
                retryable=True,
                status=response.status_code,
            )
        if response.status_code >= 400:
            raise HootsuiteError(
                "provider_error",
                "Hootsuite rejected the request",
                status=response.status_code,
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise HootsuiteError(
                "provider_error",
                "Hootsuite returned invalid JSON",
                status=response.status_code,
            ) from exc

    async def profiles(self, correlation_id: str) -> Any:
        return await self.request(
            "GET", "socialProfiles", correlation_id=correlation_id
        )

    async def profile(self, profile_id: str, correlation_id: str) -> Any:
        return await self.request(
            "GET", f"socialProfiles/{profile_id}", correlation_id=correlation_id
        )

    async def create_message(
        self, payload: Mapping[str, Any], correlation_id: str
    ) -> Any:
        return await self.request(
            "POST", "messages", json=dict(payload), correlation_id=correlation_id
        )

    async def get_message(self, message_id: str, correlation_id: str) -> Any:
        return await self.request(
            "GET", f"messages/{message_id}", correlation_id=correlation_id
        )

    async def delete_message(self, message_id: str, correlation_id: str) -> Any:
        return await self.request(
            "DELETE", f"messages/{message_id}", correlation_id=correlation_id
        )

    async def create_media(
        self, payload: Mapping[str, Any], correlation_id: str
    ) -> Any:
        return await self.request(
            "POST", "media", json=dict(payload), correlation_id=correlation_id
        )

    async def media_status(self, media_id: str, correlation_id: str) -> Any:
        return await self.request(
            "GET", f"media/{media_id}", correlation_id=correlation_id
        )
