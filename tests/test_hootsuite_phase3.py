import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest

from app.core.config import settings
from app.integrations.hootsuite.client import HootsuiteClient
from app.integrations.hootsuite.exceptions import HootsuiteError
from app.integrations.hootsuite.oauth import HootsuiteOAuth, OAuthToken, TokenFileStore
from app.social.adapters import HootsuiteProviderAdapter
from app.social.domain import Capability, ProviderName, SocialPost, SocialPostStatus
from app.social.providers import SocialError, SocialProviderRegistry
from app.social.service import SocialPublishingService


class FakeClient:
    def __init__(self) -> None:
        self.created = 0
        self.deleted = 0

    async def profiles(self, correlation_id):
        return {
            "data": [
                {
                    "id": "hs-1",
                    "type": "TWITTER",
                    "socialNetworkId": "x-1",
                    "socialNetworkUsername": "test",
                    "isReauthRequired": 0,
                }
            ]
        }

    async def profile(self, profile_id, correlation_id):
        return {
            "data": {
                "id": profile_id,
                "type": "LINKEDIN",
                "socialNetworkId": "li-1",
                "socialNetworkUsername": "test",
                "isReauthRequired": 1,
            }
        }

    async def create_message(self, payload, correlation_id):
        self.created += 1
        return {
            "data": [
                {"id": "message-1", "state": "SCHEDULED", "requestId": "request-1"}
            ]
        }

    async def get_message(self, message_id, correlation_id):
        return {"data": {"id": message_id, "state": "SENT"}}

    async def delete_message(self, message_id, correlation_id):
        self.deleted += 1
        return {}

    async def create_media(self, payload, correlation_id):
        return {"data": {"id": "media-1", "uploadUrl": "https://upload.invalid/signed"}}


def test_oauth_state_is_bound_and_tampering_fails(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 2_000_000_000)
    oauth = HootsuiteOAuth(
        "client", "secret", "https://callback.invalid", "state-secret"
    )
    url = oauth.authorization_url("tenant-a")
    query = parse_qs(urlparse(url).query)
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["offline"]
    state = query["state"][0]
    assert state.startswith("tenant-a.2000000000.")
    assert oauth._verify_signature(state, max_age_seconds=600) == "tenant-a"
    with pytest.raises(HootsuiteError):
        oauth._verify_signature(state + "tampered", max_age_seconds=600)


def test_oauth_exchange_and_refresh_use_basic_auth():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            request=request,
            json={
                "access_token": "synthetic-access",
                "refresh_token": "synthetic-refresh",
                "expires_in": 3600,
            },
        )

    oauth = HootsuiteOAuth(
        "client",
        "secret",
        "https://callback.invalid",
        "state",
        transport=httpx.MockTransport(handler),
    )
    first = asyncio.run(oauth.exchange_code("synthetic-code"))
    second = asyncio.run(oauth.refresh(first.refresh_token))
    assert first.access_token == second.access_token
    assert all(call.headers["Authorization"].startswith("Basic ") for call in calls)
    assert b"client" not in calls[0].content and b"secret" not in calls[0].content


def test_token_file_requires_private_permissions(tmp_path: Path):
    path = tmp_path / "token.json"
    store = TokenFileStore(str(path))
    store.save(
        OAuthToken("synthetic-access", "synthetic-refresh", 2_000_000_000, "offline")
    )
    assert path.stat().st_mode & 0o777 == 0o600
    assert store.load() is not None
    path.chmod(0o644)
    with pytest.raises(HootsuiteError):
        store.load()


def test_client_normalizes_rate_limit_and_unknown_result(tmp_path: Path, monkeypatch):
    token_file = tmp_path / "token.json"
    TokenFileStore(str(token_file)).save(
        OAuthToken("synthetic-access", "", int(time.time()) + 3600)
    )
    monkeypatch.setattr(settings, "hootsuite_token_file", str(token_file))

    async def rate_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request, headers={"Retry-After": "12"})

    with pytest.raises(HootsuiteError) as rate:
        asyncio.run(HootsuiteClient(httpx.MockTransport(rate_handler)).profiles("test"))
    assert rate.value.code == "rate_limit" and rate.value.retry_after == 12

    async def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic", request=request)

    with pytest.raises(HootsuiteError) as unknown:
        asyncio.run(
            HootsuiteClient(httpx.MockTransport(timeout_handler)).create_message(
                {}, "test"
            )
        )
    assert unknown.value.unknown_result is True and unknown.value.retryable is False


def test_adapter_capabilities_accounts_schedule_cancel_and_reconcile(monkeypatch):
    monkeypatch.setattr(settings, "hootsuite_enabled", True)
    client = FakeClient()
    adapter = HootsuiteProviderAdapter(client)  # type: ignore[arg-type]
    assert Capability.POST_UPDATE not in adapter.get_capabilities()
    assert Capability.WEBHOOK_EVENTS not in adapter.get_capabilities()
    accounts = asyncio.run(adapter.list_accounts())
    assert accounts[0]["network"] == "x"
    post = SocialPost(
        uuid4(),
        ProviderName.HOOTSUITE,
        (uuid4(),),
        {"text": "NON-PRODUCTION"},
        publish_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    result = asyncio.run(adapter.create_post(post, ["hs-1"], "correlation"))
    assert result.status is SocialPostStatus.SCHEDULED and client.created == 1
    post.provider_post_id = result.provider_post_id
    assert (
        asyncio.run(adapter.get_post_status("message-1")).status
        is SocialPostStatus.PUBLISHED
    )
    assert (
        asyncio.run(adapter.cancel_post(post, "correlation")).status
        is SocialPostStatus.CANCELLED
    )
    assert client.deleted == 1
    media = asyncio.run(
        adapter.upload_media({"content_type": "image/png", "size": 100}, "correlation")
    )
    assert media["status"] == "UPLOAD_PENDING"


def test_canary_routes_only_new_allowlisted_posts_and_preserves_history(monkeypatch):
    class Adapter(HootsuiteProviderAdapter):
        pass

    registry = SocialProviderRegistry()
    registry.register(Adapter(FakeClient()))  # type: ignore[arg-type]
    service = SocialPublishingService(registry)
    canary = uuid4()
    other = uuid4()
    monkeypatch.setattr(settings, "social_provider", "postly")
    monkeypatch.setattr(settings, "social_provider_migration_mode", "canary")
    monkeypatch.setattr(settings, "hootsuite_canary_account_ids", str(canary))
    monkeypatch.setattr(settings, "hootsuite_enabled", True)
    assert service.resolve_provider(account_ids=(canary,)) is ProviderName.HOOTSUITE
    assert service.resolve_provider(account_ids=(other,)) is ProviderName.POSTLY
    historical = SocialPost(
        uuid4(), ProviderName.POSTLY, (canary,), {"text": "historical"}
    )
    assert service.resolve_provider(historical, (canary,)) is ProviderName.POSTLY
    monkeypatch.setattr(settings, "hootsuite_enabled", False)
    with pytest.raises(SocialError):
        service.resolve_provider(account_ids=(canary,))


def test_defaults_remain_fail_closed():
    assert settings.hootsuite_enabled is False
    assert settings.social_provider == "disabled"
    assert settings.social_provider_migration_mode == "disabled"
    assert settings.social_publish_enabled is False
    assert settings.social_odoo_write_enabled is False
