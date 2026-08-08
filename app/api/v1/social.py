from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.social.adapters import HootsuiteProviderAdapter, PostlyProviderAdapter
from app.social.domain import Capability, JobType
from app.social.providers import SocialError, SocialProviderRegistry
from app.social.service import SocialPublishingService


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MediaReference(StrictModel):
    asset_id: UUID


class Content(StrictModel):
    text: str = Field(min_length=1, max_length=10000)
    media: list[MediaReference] = Field(default_factory=list, max_length=50)


class Schedule(StrictModel):
    publish_at: datetime


class CreateSocialPost(StrictModel):
    id: UUID | None = None
    tenant_id: UUID
    campaign_id: UUID | None = None
    accounts: list[UUID] = Field(min_length=1, max_length=50)
    content: Content
    schedule: Schedule | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateSocialPost(StrictModel):
    content: Content | None = None
    metadata: dict[str, Any] | None = None


class CreateCampaign(StrictModel):
    tenant_id: UUID
    name: str = Field(min_length=1, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)


registry = SocialProviderRegistry()
registry.register(PostlyProviderAdapter())
registry.register(HootsuiteProviderAdapter())
service = SocialPublishingService(registry)
campaign_store: dict[UUID, dict[str, Any]] = {}
router = APIRouter(prefix="/api/v1/social", tags=["social"])


def _error(exc: SocialError) -> HTTPException:
    return HTTPException(
        exc.status_code,
        {"code": exc.code, "message": exc.safe_message, "retryable": exc.retryable},
    )


def _require(permission: str, supplied: str | None) -> None:
    permissions = {item.strip() for item in (supplied or "").split(",") if item.strip()}
    if permission not in permissions and "social.admin" not in permissions:
        raise HTTPException(
            403,
            {
                "code": "SOCIAL_PERMISSION_DENIED",
                "message": f"Permission {permission} is required",
            },
        )


def _ids(request: Request) -> tuple[str, str]:
    return (
        request.headers.get("X-Correlation-ID") or str(uuid4()),
        request.headers.get("X-Request-ID") or str(uuid4()),
    )


def _post(post: Any) -> dict[str, Any]:
    return {
        "id": post.id,
        "tenant_id": post.tenant_id,
        "campaign_id": post.campaign_id,
        "accounts": post.account_ids,
        "content": post.content,
        "schedule": {"publish_at": post.publish_at} if post.publish_at else None,
        "provider": post.provider,
        "status": post.status,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }


@router.get("/providers")
async def providers(
    x_codestra_permissions: str | None = Header(None),
) -> list[dict[str, Any]]:
    _require("social.read", x_codestra_permissions)
    return [
        {"provider": item.name, "capabilities": sorted(item.get_capabilities())}
        for item in registry.providers()
    ]


@router.get("/providers/{provider}")
async def provider(
    provider: str, x_codestra_permissions: str | None = Header(None)
) -> dict[str, Any]:
    _require("social.read", x_codestra_permissions)
    try:
        adapter = registry.get(provider)
        result = await adapter.health_check()
        result["capabilities"] = sorted(adapter.get_capabilities())
        return result
    except SocialError as exc:
        raise _error(exc) from exc


@router.get("/accounts")
async def accounts(
    x_codestra_permissions: str | None = Header(None),
) -> list[dict[str, Any]]:
    _require("social.accounts.read", x_codestra_permissions)
    return [
        {
            "id": item.id,
            "provider": item.provider,
            "network": item.network,
            "external_profile_name": item.external_profile_name,
            "external_profile_id": item.external_profile_id,
            "connection_state": item.connection_state,
            "capabilities": sorted(item.capabilities),
            "last_sync_at": item.last_sync_at,
        }
        for item in service.repository.accounts.values()
    ]


@router.get("/accounts/{account_id}")
async def account(
    account_id: UUID, x_codestra_permissions: str | None = Header(None)
) -> dict[str, Any]:
    _require("social.accounts.read", x_codestra_permissions)
    try:
        item = service.repository.accounts[account_id]
    except KeyError as exc:
        raise HTTPException(
            404,
            {
                "code": "SOCIAL_ACCOUNT_NOT_FOUND",
                "message": "Social account was not found",
            },
        ) from exc
    return {
        "id": item.id,
        "provider": item.provider,
        "network": item.network,
        "external_profile_name": item.external_profile_name,
        "external_profile_id": item.external_profile_id,
        "connection_state": item.connection_state,
        "capabilities": sorted(item.capabilities),
        "last_sync_at": item.last_sync_at,
    }


@router.post("/posts", status_code=202)
async def create_post(
    body: CreateSocialPost,
    request: Request,
    response: Response,
    idempotency_key: str = Header(min_length=1, max_length=255),
    x_codestra_permissions: str | None = Header(None),
) -> dict[str, Any]:
    _require("social.write", x_codestra_permissions)
    correlation_id, request_id = _ids(request)
    try:
        post, job, created = await service.create_post(
            tenant_id=body.tenant_id,
            account_ids=tuple(body.accounts),
            content=body.content.model_dump(mode="json"),
            campaign_id=body.campaign_id,
            publish_at=body.schedule.publish_at if body.schedule else None,
            metadata=body.metadata,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_id=request_id,
            post_id=body.id,
        )
    except SocialError as exc:
        raise _error(exc) from exc
    response.headers["X-Correlation-ID"] = correlation_id
    return {"post": _post(post), "job_id": job.id, "idempotent_replay": not created}


@router.get("/posts/{post_id}")
async def get_post(
    post_id: UUID, x_codestra_permissions: str | None = Header(None)
) -> dict[str, Any]:
    _require("social.read", x_codestra_permissions)
    try:
        return _post(service.repository.posts[post_id])
    except KeyError as exc:
        raise HTTPException(
            404,
            {"code": "SOCIAL_POST_NOT_FOUND", "message": "Social post was not found"},
        ) from exc


@router.patch("/posts/{post_id}")
async def update_post(
    post_id: UUID,
    body: UpdateSocialPost,
    x_codestra_permissions: str | None = Header(None),
) -> dict[str, Any]:
    _require("social.write", x_codestra_permissions)
    try:
        post = service.repository.posts[post_id]
    except KeyError as exc:
        raise HTTPException(
            404,
            {"code": "SOCIAL_POST_NOT_FOUND", "message": "Social post was not found"},
        ) from exc
    if post.status not in {"DRAFT", "QUEUED", "SCHEDULED"}:
        raise HTTPException(
            409,
            {
                "code": "SOCIAL_POST_NOT_EDITABLE",
                "message": "Social post cannot be edited in its current state",
            },
        )
    if body.content is not None:
        post.content = body.content.model_dump(mode="json")
    if body.metadata is not None:
        post.metadata = body.metadata
    post.updated_at = datetime.now(timezone.utc)
    return _post(post)


@router.post("/media", status_code=202)
async def media(x_codestra_permissions: str | None = Header(None)) -> dict[str, Any]:
    _require("social.write", x_codestra_permissions)
    raise HTTPException(
        503,
        {
            "code": "SOCIAL_PROVIDER_DISABLED",
            "message": "Social media upload is disabled",
        },
    )


@router.post("/campaigns", status_code=201)
async def create_campaign(
    body: CreateCampaign, x_codestra_permissions: str | None = Header(None)
) -> dict[str, Any]:
    _require("social.write", x_codestra_permissions)
    campaign_id = uuid4()
    campaign_store[campaign_id] = {
        "id": campaign_id,
        "tenant_id": body.tenant_id,
        "name": body.name,
        "status": "DRAFT",
        "metadata": body.metadata,
        "created_at": datetime.now(timezone.utc),
    }
    return campaign_store[campaign_id]


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: UUID, x_codestra_permissions: str | None = Header(None)
) -> dict[str, Any]:
    _require("social.read", x_codestra_permissions)
    try:
        return campaign_store[campaign_id]
    except KeyError as exc:
        raise HTTPException(
            404,
            {
                "code": "SOCIAL_CAMPAIGN_NOT_FOUND",
                "message": "Social campaign was not found",
            },
        ) from exc


@router.get("/analytics")
async def analytics(
    x_codestra_permissions: str | None = Header(None),
) -> dict[str, Any]:
    _require("social.analytics.read", x_codestra_permissions)
    return {"items": [], "sync_enabled": False}


async def _command(
    post_id: UUID,
    action: JobType,
    request: Request,
    idempotency_key: str,
    permission: str,
    supplied: str | None,
) -> dict[str, Any]:
    _require(permission, supplied)
    correlation_id, request_id = _ids(request)
    try:
        job, created = await service.command(
            post_id, action, idempotency_key, correlation_id, request_id
        )
    except SocialError as exc:
        raise _error(exc) from exc
    return {
        "post_id": post_id,
        "job_id": job.id,
        "status": job.state.upper(),
        "idempotent_replay": not created,
    }


@router.post("/posts/{post_id}/schedule", status_code=202)
async def schedule(
    post_id: UUID,
    request: Request,
    idempotency_key: str = Header(min_length=1, max_length=255),
    x_codestra_permissions: str | None = Header(None),
) -> dict[str, Any]:
    return await _command(
        post_id,
        JobType.SCHEDULE,
        request,
        idempotency_key,
        "social.schedule",
        x_codestra_permissions,
    )


@router.post("/posts/{post_id}/publish", status_code=202)
async def publish(
    post_id: UUID,
    request: Request,
    idempotency_key: str = Header(min_length=1, max_length=255),
    x_codestra_permissions: str | None = Header(None),
) -> dict[str, Any]:
    return await _command(
        post_id,
        JobType.PUBLISH,
        request,
        idempotency_key,
        "social.publish",
        x_codestra_permissions,
    )


@router.post("/posts/{post_id}/cancel", status_code=202)
async def cancel(
    post_id: UUID,
    request: Request,
    idempotency_key: str = Header(min_length=1, max_length=255),
    x_codestra_permissions: str | None = Header(None),
) -> dict[str, Any]:
    return await _command(
        post_id,
        JobType.CANCEL,
        request,
        idempotency_key,
        "social.cancel",
        x_codestra_permissions,
    )


@router.delete("/posts/{post_id}", status_code=202)
async def delete(
    post_id: UUID,
    request: Request,
    idempotency_key: str = Header(min_length=1, max_length=255),
    x_codestra_permissions: str | None = Header(None),
) -> dict[str, Any]:
    return await _command(
        post_id,
        JobType.DELETE,
        request,
        idempotency_key,
        "social.delete",
        x_codestra_permissions,
    )


@router.post("/webhooks/{provider}", status_code=202)
async def webhook(provider: str, request: Request) -> dict[str, Any]:
    body = await request.body()
    correlation_id, _ = _ids(request)
    try:
        adapter = registry.require(provider, capability=Capability.WEBHOOK_EVENTS)
        await adapter.verify_webhook(body, request.headers)
        payload = json.loads(body)
        event_id = str(payload.get("id", ""))
        if not event_id:
            raise SocialError(
                "SOCIAL_WEBHOOK_INVALID",
                "Webhook event ID is required",
                status_code=422,
            )
        if event_id in service.repository.webhook_ids:
            return {"accepted": True, "duplicate": True}
        event = await adapter.normalize_webhook(payload, correlation_id)
        service.repository.webhook_ids.add(event_id)
        return {
            "accepted": True,
            "duplicate": False,
            "event_id": event.event_id,
            "event_type": event.event_type,
            "occurred_at": datetime.now(timezone.utc),
        }
    except (SocialError, json.JSONDecodeError) as exc:
        if isinstance(exc, SocialError):
            raise _error(exc) from exc
        raise HTTPException(
            422,
            {"code": "SOCIAL_WEBHOOK_INVALID", "message": "Webhook payload is invalid"},
        ) from exc
