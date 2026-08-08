from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.integrations.postiz.client import PostizClient
from app.integrations.postiz.exceptions import PostizError
from app.integrations.hootsuite.client import HootsuiteClient
from app.integrations.hootsuite.exceptions import HootsuiteError
from app.social.domain import (
    Capability,
    NormalizedEvent,
    ProviderName,
    ProviderResult,
    SocialPost,
    SocialPostStatus,
    normalize_network,
)
from app.social.providers import SocialError, SocialProviderAdapter


POSTLY_CAPABILITIES = frozenset(
    {
        Capability.POST_CREATE,
        Capability.POST_DELETE,
        Capability.POST_SCHEDULE,
        Capability.POST_CANCEL,
        Capability.POST_PUBLISH,
        Capability.MEDIA_UPLOAD,
        Capability.IMAGE_POST,
        Capability.VIDEO_POST,
        Capability.MULTI_IMAGE,
        Capability.ANALYTICS,
        Capability.WEBHOOK_EVENTS,
    }
)


STATUS_MAP = {
    "draft": SocialPostStatus.DRAFT,
    "queued": SocialPostStatus.QUEUED,
    "scheduled": SocialPostStatus.SCHEDULED,
    "publishing": SocialPostStatus.PUBLISHING,
    "published": SocialPostStatus.PUBLISHED,
    "failed": SocialPostStatus.FAILED,
    "cancelled": SocialPostStatus.CANCELLED,
    "canceled": SocialPostStatus.CANCELLED,
    "deleted": SocialPostStatus.DELETED,
    "requires_action": SocialPostStatus.REQUIRES_ACTION,
}


def normalize_status(value: str | None) -> SocialPostStatus:
    return STATUS_MAP.get((value or "").strip().lower(), SocialPostStatus.UNKNOWN)


def map_postiz_error(exc: PostizError) -> SocialError:
    mappings = {
        "not_configured": ("SOCIAL_PROVIDER_NOT_CONFIGURED", 503),
        "authentication": ("SOCIAL_PROVIDER_AUTH_FAILED", 502),
        "rate_limit": ("SOCIAL_PROVIDER_RATE_LIMITED", 503),
        "temporary": ("SOCIAL_PROVIDER_UNAVAILABLE", 503),
        "unknown_result": ("SOCIAL_PROVIDER_UNKNOWN_RESULT", 503),
    }
    code, status = mappings.get(exc.code, ("SOCIAL_PUBLISH_FAILED", 502))
    return SocialError(
        code,
        "Social provider request failed",
        retryable=exc.retryable,
        status_code=status,
        unknown_result=exc.unknown_result,
    )


class PostlyProviderAdapter(SocialProviderAdapter):
    """Postly/Postiz boundary. No provider payload escapes this adapter."""

    name = ProviderName.POSTLY

    def __init__(self, client: PostizClient | None = None) -> None:
        self.client = client or PostizClient()

    def get_capabilities(self) -> frozenset[Capability]:
        return POSTLY_CAPABILITIES

    async def health_check(self) -> dict[str, Any]:
        configured = bool(
            settings.postiz_internal_base_url and settings.postiz_api_key_file
        )
        if not configured:
            return {
                "provider": self.name,
                "configured": False,
                "enabled": False,
                "reachable": False,
                "status": "NOT_CONFIGURED",
            }
        if not settings.postiz_delivery_enabled:
            return {
                "provider": self.name,
                "configured": True,
                "enabled": False,
                "reachable": None,
                "status": "DISABLED",
            }
        try:
            await self.client.connection_check("social-health-check")
        except PostizError:
            return {
                "provider": self.name,
                "configured": True,
                "enabled": True,
                "reachable": False,
                "status": "UNAVAILABLE",
            }
        return {
            "provider": self.name,
            "configured": True,
            "enabled": True,
            "reachable": True,
            "status": "AVAILABLE",
        }

    async def list_accounts(self) -> list[dict[str, Any]]:
        try:
            result = await self.client.channels("social-account-sync")
        except PostizError as exc:
            raise map_postiz_error(exc) from exc
        items = result if isinstance(result, list) else result.get("integrations", [])
        return [
            {
                "provider_account_id": str(item.get("id", "")),
                "network": str(item.get("providerIdentifier", "other")),
                "external_profile_name": str(item.get("name", "")),
            }
            for item in items
        ]

    def _payload(
        self, post: SocialPost, account_refs: list[str], *, publish: bool
    ) -> dict[str, Any]:
        return {
            "content": post.content.get("text", ""),
            "integration": account_refs,
            "date": post.publish_at.isoformat() if post.publish_at else None,
            "type": "schedule" if post.publish_at else ("now" if publish else "draft"),
            "settings": post.metadata.get("provider", {}),
        }

    async def _create(
        self, post: SocialPost, refs: list[str], correlation_id: str, *, publish: bool
    ) -> ProviderResult:
        try:
            raw = await self.client.create_post(
                self._payload(post, refs, publish=publish), correlation_id
            )
        except PostizError as exc:
            raise map_postiz_error(exc) from exc
        provider_id = str(raw.get("id") or raw.get("postId") or "") or None
        default = (
            SocialPostStatus.SCHEDULED
            if post.publish_at
            else (SocialPostStatus.PUBLISHED if publish else SocialPostStatus.DRAFT)
        )
        return ProviderResult(
            provider_id,
            normalize_status(raw.get("status")) if raw.get("status") else default,
        )

    async def create_post(
        self, post: SocialPost, account_refs: list[str], correlation_id: str
    ) -> ProviderResult:
        return await self._create(post, account_refs, correlation_id, publish=False)

    async def schedule_post(
        self, post: SocialPost, correlation_id: str
    ) -> ProviderResult:
        return await self._create(post, [], correlation_id, publish=False)

    async def publish_post(
        self, post: SocialPost, correlation_id: str
    ) -> ProviderResult:
        return await self._create(post, [], correlation_id, publish=True)

    async def cancel_post(
        self, post: SocialPost, correlation_id: str
    ) -> ProviderResult:
        if not post.provider_post_id:
            raise SocialError(
                "SOCIAL_POST_NOT_SYNCHRONIZED",
                "Social post has no provider reference",
                status_code=409,
            )
        try:
            await self.client.cancel_post(post.provider_post_id, correlation_id)
        except PostizError as exc:
            raise map_postiz_error(exc) from exc
        return ProviderResult(post.provider_post_id, SocialPostStatus.CANCELLED)

    async def delete_post(
        self, post: SocialPost, correlation_id: str
    ) -> ProviderResult:
        return await self.cancel_post(post, correlation_id)

    async def upload_media(
        self, media: Mapping[str, Any], correlation_id: str
    ) -> dict[str, Any]:
        source_url = str(media.get("source_url", ""))
        if not source_url:
            raise SocialError(
                "SOCIAL_MEDIA_INVALID", "A source URL is required", status_code=422
            )
        try:
            raw = await self.client.upload_from_url(source_url, correlation_id)
        except PostizError as exc:
            raise map_postiz_error(exc) from exc
        return {"provider_media_id": str(raw.get("id", "")), "status": "UPLOADED"}

    async def verify_webhook(self, body: bytes, headers: Mapping[str, str]) -> None:
        secret = settings.postly_webhook_secret
        if not secret:
            raise SocialError(
                "SOCIAL_PROVIDER_NOT_CONFIGURED",
                "Webhook verification is not configured",
                status_code=503,
            )
        timestamp = headers.get("x-postly-timestamp", "")
        signature = headers.get("x-postly-signature", "")
        try:
            if abs(time.time() - int(timestamp)) > settings.social_webhook_ttl_seconds:
                raise ValueError
        except ValueError as exc:
            raise SocialError(
                "SOCIAL_WEBHOOK_INVALID_SIGNATURE",
                "Webhook timestamp is invalid",
                status_code=401,
            ) from exc
        expected = hmac.new(
            secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, signature.removeprefix("sha256=")):
            raise SocialError(
                "SOCIAL_WEBHOOK_INVALID_SIGNATURE",
                "Webhook signature is invalid",
                status_code=401,
            )

    async def normalize_webhook(
        self, payload: Mapping[str, Any], correlation_id: str
    ) -> NormalizedEvent:
        event_map = {
            "post.published": "social.post.published",
            "post.failed": "social.post.failed",
            "post.scheduled": "social.post.scheduled",
            "post.cancelled": "social.post.cancelled",
            "account.connected": "social.account.connected",
            "account.disconnected": "social.account.disconnected",
            "comment.created": "social.comment.received",
            "message.created": "social.message.received",
        }
        event_type = event_map.get(str(payload.get("type", "")))
        if not event_type:
            raise SocialError(
                "SOCIAL_WEBHOOK_EVENT_UNSUPPORTED",
                "Webhook event is unsupported",
                status_code=422,
            )
        try:
            subject_id = UUID(str(payload["codestra_subject_id"]))
            tenant_id = UUID(str(payload["tenant_id"]))
        except (KeyError, ValueError) as exc:
            raise SocialError(
                "SOCIAL_WEBHOOK_INVALID",
                "Webhook identifiers are invalid",
                status_code=422,
            ) from exc
        safe_payload = {
            key: payload[key]
            for key in ("status", "provider_post_id", "metrics")
            if key in payload
        }
        return NormalizedEvent(
            event_type, self.name, subject_id, correlation_id, tenant_id, safe_payload
        )


class HootsuiteProviderAdapter(SocialProviderAdapter):
    name = ProviderName.HOOTSUITE

    CAPABILITIES = frozenset(
        {
            Capability.POST_CREATE,
            Capability.POST_DELETE,
            Capability.POST_SCHEDULE,
            Capability.POST_CANCEL,
            Capability.POST_PUBLISH,
            Capability.MEDIA_UPLOAD,
            Capability.IMAGE_POST,
            Capability.MULTI_IMAGE,
            Capability.VIDEO_POST,
        }
    )

    STATUS_MAP = {
        "PENDING_APPROVAL": SocialPostStatus.REQUIRES_ACTION,
        "REJECTED": SocialPostStatus.FAILED,
        "SENT": SocialPostStatus.PUBLISHED,
        "SCHEDULED": SocialPostStatus.SCHEDULED,
        "SEND_FAILED_PERMANENTLY": SocialPostStatus.FAILED,
    }

    def __init__(self, client: HootsuiteClient | None = None) -> None:
        self.client = client or HootsuiteClient()

    @staticmethod
    def _ensure_enabled() -> None:
        if not settings.hootsuite_enabled:
            raise SocialError(
                "SOCIAL_PROVIDER_DISABLED", "Hootsuite is disabled", status_code=503
            )

    def get_capabilities(self) -> frozenset[Capability]:
        return self.CAPABILITIES

    @staticmethod
    def _map_error(exc: HootsuiteError) -> SocialError:
        mappings = {
            "not_configured": ("SOCIAL_PROVIDER_NOT_CONFIGURED", 503),
            "authentication": ("SOCIAL_PROVIDER_AUTH_FAILED", 502),
            "rate_limit": ("SOCIAL_PROVIDER_RATE_LIMITED", 503),
            "temporary": ("SOCIAL_PROVIDER_UNAVAILABLE", 503),
            "unknown_result": ("SOCIAL_PROVIDER_UNKNOWN_RESULT", 503),
            "not_found": ("SOCIAL_ACCOUNT_NOT_FOUND", 404),
        }
        code, status = mappings.get(exc.code, ("SOCIAL_PUBLISH_FAILED", 502))
        return SocialError(
            code,
            "Social provider request failed",
            retryable=exc.retryable,
            status_code=status,
            unknown_result=exc.unknown_result,
        )

    async def health_check(self) -> dict[str, Any]:
        configured = bool(
            settings.hootsuite_client_id_file
            and settings.hootsuite_client_secret_file
            and settings.hootsuite_token_file
        )
        if not configured:
            return {
                "provider": self.name,
                "configured": False,
                "enabled": False,
                "reachable": None,
                "status": "NOT_CONFIGURED",
            }
        if not settings.hootsuite_enabled:
            return {
                "provider": self.name,
                "configured": True,
                "enabled": False,
                "reachable": None,
                "status": "DISABLED",
            }
        try:
            await self.client.profiles("social-health-check")
        except HootsuiteError:
            return {
                "provider": self.name,
                "configured": True,
                "enabled": True,
                "reachable": False,
                "status": "UNAVAILABLE",
            }
        return {
            "provider": self.name,
            "configured": True,
            "enabled": True,
            "reachable": True,
            "status": "AVAILABLE",
        }

    async def list_accounts(self) -> list[dict[str, Any]]:
        self._ensure_enabled()
        try:
            raw = await self.client.profiles("social-account-sync")
        except HootsuiteError as exc:
            raise self._map_error(exc) from exc
        items = raw.get("data", []) if isinstance(raw, dict) else []
        return [
            {
                "provider_account_id": str(item.get("id") or ""),
                "network": normalize_network(str(item.get("type") or "other")).value,
                "external_profile_name": str(item.get("socialNetworkUsername") or ""),
                "external_profile_id": str(item.get("socialNetworkId") or ""),
                "connection_state": "authentication_required"
                if bool(item.get("isReauthRequired"))
                else "connected",
            }
            for item in items
        ]

    async def get_account(self, provider_account_id: str) -> dict[str, Any]:
        self._ensure_enabled()
        try:
            raw = await self.client.profile(provider_account_id, "social-account-get")
        except HootsuiteError as exc:
            raise self._map_error(exc) from exc
        item = raw.get("data", raw)
        return {
            "provider_account_id": str(item.get("id") or ""),
            "network": normalize_network(str(item.get("type") or "other")).value,
            "external_profile_name": str(item.get("socialNetworkUsername") or ""),
            "external_profile_id": str(item.get("socialNetworkId") or ""),
            "connection_state": "authentication_required"
            if bool(item.get("isReauthRequired"))
            else "connected",
        }

    @staticmethod
    def _message(raw: Any, default: SocialPostStatus) -> ProviderResult:
        items = raw.get("data", []) if isinstance(raw, dict) else []
        item = items[0] if isinstance(items, list) and items else (items if isinstance(items, dict) else {})
        provider_id = str(item.get("id") or "") or None
        status = HootsuiteProviderAdapter.STATUS_MAP.get(str(item.get("state") or "").upper(), default)
        return ProviderResult(provider_id, status, {"provider_request_id": item.get("requestId")})

    async def create_post(
        self, post: SocialPost, account_refs: list[str], correlation_id: str
    ) -> ProviderResult:
        self._ensure_enabled()
        if not account_refs:
            raise SocialError("SOCIAL_ACCOUNT_NOT_FOUND", "A Hootsuite profile is required", status_code=422)
        payload: dict[str, Any] = {
            "text": str(post.content.get("text") or ""),
            "socialProfileIds": account_refs,
        }
        if post.publish_at:
            payload["scheduledSendTime"] = post.publish_at.isoformat().replace("+00:00", "Z")
        media = post.metadata.get("hootsuite_media_ids")
        if media:
            payload["media"] = [{"id": str(item)} for item in media]
        try:
            raw = await self.client.create_message(payload, correlation_id)
        except HootsuiteError as exc:
            raise self._map_error(exc) from exc
        return self._message(raw, SocialPostStatus.SCHEDULED if post.publish_at else SocialPostStatus.PUBLISHING)

    async def schedule_post(self, post: SocialPost, correlation_id: str) -> ProviderResult:
        refs = [str(item) for item in post.metadata.get("provider_account_refs", [])]
        return await self.create_post(post, refs, correlation_id)

    async def publish_post(self, post: SocialPost, correlation_id: str) -> ProviderResult:
        refs = [str(item) for item in post.metadata.get("provider_account_refs", [])]
        return await self.create_post(post, refs, correlation_id)

    async def get_post(self, provider_post_id: str) -> ProviderResult:
        self._ensure_enabled()
        try:
            raw = await self.client.get_message(provider_post_id, "social-reconcile")
        except HootsuiteError as exc:
            raise self._map_error(exc) from exc
        return self._message(raw, SocialPostStatus.UNKNOWN)

    async def get_post_status(self, provider_post_id: str) -> ProviderResult:
        return await self.get_post(provider_post_id)

    async def cancel_post(self, post: SocialPost, correlation_id: str) -> ProviderResult:
        self._ensure_enabled()
        if not post.provider_post_id:
            raise SocialError("SOCIAL_POST_NOT_SYNCHRONIZED", "Social post has no provider reference", status_code=409)
        try:
            await self.client.delete_message(post.provider_post_id, correlation_id)
        except HootsuiteError as exc:
            raise self._map_error(exc) from exc
        return ProviderResult(post.provider_post_id, SocialPostStatus.CANCELLED)

    async def delete_post(self, post: SocialPost, correlation_id: str) -> ProviderResult:
        result = await self.cancel_post(post, correlation_id)
        return ProviderResult(result.provider_post_id, SocialPostStatus.DELETED)

    async def upload_media(self, media: Mapping[str, Any], correlation_id: str) -> dict[str, Any]:
        self._ensure_enabled()
        mime = str(media.get("content_type") or "")
        size = int(media.get("size") or 0)
        if not (mime.startswith("image/") or mime.startswith("video/")) or size <= 0:
            raise SocialError("SOCIAL_MEDIA_INVALID", "Media type or size is invalid", status_code=422)
        try:
            raw = await self.client.create_media({"mimeType": mime, "sizeBytes": size}, correlation_id)
        except HootsuiteError as exc:
            raise self._map_error(exc) from exc
        item = raw.get("data", raw)
        return {
            "provider_media_id": str(item.get("id") or ""),
            "upload_url": str(item.get("uploadUrl") or ""),
            "status": "UPLOAD_PENDING",
        }
