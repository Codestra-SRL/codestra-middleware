"""Mock-only social control-plane routes; no provider network writes."""

import hashlib
import hmac
import ipaddress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.social_postly import SocialControlPlane, SocialError, serialize_job
from app.core.social_repository import SocialRepository
from app.db.session import get_session
from app.metrics import SOCIAL_CALLBACKS

router = APIRouter(prefix="/api/v1/social", tags=["social-mock"])
control = SocialControlPlane()


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    content_job_id: str = Field(min_length=1)
    content_version: int = Field(ge=1)
    integration_ids: list[str] = Field(min_length=1)
    scheduled_at: datetime
    preferred_language: Literal["en", "es", "fr", "ht"] = "en"
    correlation_id: str = Field(min_length=1, max_length=128)


class GeneratedContentProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content_job_id: str
    content_version: int = Field(ge=1)
    language: Literal["en", "es", "fr", "ht"]
    caption: str = Field(max_length=10_000)
    status: Literal["proposal_only"]
    hashtags: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    content_version: int = Field(ge=1)


class ProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    integration_id: str = Field(min_length=1)
    state: Literal[
        "accepted",
        "media_uploaded",
        "scheduled",
        "publishing",
        "published",
        "partially_published",
        "failed",
        "cancelled",
        "unknown_requires_reconciliation",
    ]
    provider_release_id: str | None = None
    error: dict[str, Any] | None = None


class ProviderCallback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callback_id: UUID
    attempt: int = Field(ge=1)
    event_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    state: Literal[
        "accepted",
        "media_uploaded",
        "scheduled",
        "publishing",
        "published",
        "partially_published",
        "failed",
        "cancelled",
        "unknown_requires_reconciliation",
    ]
    occurred_at: datetime
    postly_group_id: str | None = None
    provider_results: list[ProviderResult] = Field(min_length=1)
    error: dict[str, Any] | None = None


class RequestScope(BaseModel):
    organization_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)


def request_scope(
    organization_id: str = Header(alias="X-Organization-ID"),
    workspace_id: str = Header(alias="X-Workspace-ID"),
) -> RequestScope:
    return RequestScope(
        organization_id=organization_id,
        workspace_id=workspace_id,
    )


def _check_scope(scope: RequestScope, organization_id: str, workspace_id: str) -> None:
    if scope.organization_id != organization_id or scope.workspace_id != workspace_id:
        raise HTTPException(403, "organization/workspace scope mismatch")


def _mock_job(job_id: str, scope: RequestScope):
    job = _call(lambda: control._get(job_id))
    if (
        scope.organization_id != job.organization_id
        or scope.workspace_id != job.workspace_id
    ):
        raise HTTPException(404, "social job not found")
    return job


def _callback_secret() -> bytes:
    path = Path(settings.postly_callback_hmac_file)
    if not path.is_absolute() or not path.is_file():
        raise HTTPException(503, "provider callback secret unavailable")
    secret = path.read_bytes().strip()
    if len(secret) < 32:
        raise HTTPException(503, "provider callback secret unavailable")
    return secret


def _source_allowed(request: Request) -> bool:
    source = request.client.host if request.client else ""
    try:
        address = ipaddress.ip_address(source)
        networks = [
            ipaddress.ip_network(item.strip(), strict=False)
            for item in settings.postly_callback_source_cidrs.split(",")
            if item.strip()
        ]
    except ValueError:
        return False
    return bool(networks) and any(address in network for network in networks)


def _guard() -> None:
    if settings.environment not in {"test", "staging", "integration", "preproduction"}:
        raise HTTPException(404, "social mock route unavailable")


def _call(fn):
    try:
        return fn()
    except SocialError as exc:
        raise HTTPException(
            exc.status_code, {"code": exc.code, "message": str(exc)}
        ) from exc


async def _async_call(fn):
    try:
        return await fn()
    except SocialError as exc:
        raise HTTPException(
            exc.status_code, {"code": exc.code, "message": str(exc)}
        ) from exc


@router.post("/jobs", status_code=202)
async def create_job(
    body: JobRequest,
    scope: RequestScope = Depends(request_scope),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    _guard()
    _check_scope(scope, body.organization_id, body.workspace_id)
    if settings.social_control_plane_enabled:
        return await _async_call(
            lambda: SocialRepository(db).create_job(body.model_dump())
        )
    payload = body.model_dump(mode="json")
    return serialize_job(_call(lambda: control.create(payload)))


@router.post("/jobs/{job_id}/n8n-result", status_code=202)
async def n8n_result(
    job_id: str,
    body: GeneratedContentProposal,
    scope: RequestScope = Depends(request_scope),  # noqa: B008
    execution_id: str = Header("", alias="X-N8N-Execution-ID"),
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if settings.social_control_plane_enabled:
        if not execution_id:
            raise HTTPException(422, "n8n execution identifier required")
        return await _async_call(
            lambda: SocialRepository(db).store_proposal(
                job_id,
                body.model_dump(),
                execution_id,
                scope.organization_id,
                scope.workspace_id,
            )
        )
    _mock_job(job_id, scope)
    return serialize_job(
        _call(lambda: control.accept_n8n_proposal(job_id, body.model_dump()))
    )


@router.post("/jobs/{job_id}/approve")
async def approve(
    job_id: str,
    body: ApprovalRequest,
    scope: RequestScope = Depends(request_scope),  # noqa: B008
    role: str = Header("", alias="X-Codestra-Role"),
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if role not in {"social_approver", "integration_admin"}:
        raise HTTPException(403, "social approver role required")
    if settings.social_control_plane_enabled:
        return await _async_call(
            lambda: SocialRepository(db).approve(
                job_id,
                {
                    "approval_id": body.approval_id,
                    "approved_by": body.approved_by,
                    "approved_at": datetime.now().astimezone(),
                    "content_version": body.content_version,
                },
                scope.organization_id,
                scope.workspace_id,
            )
        )
    _mock_job(job_id, scope)
    return serialize_job(
        _call(
            lambda: control.approve(
                job_id,
                approval_id=body.approval_id,
                approved_by=body.approved_by,
                content_version=body.content_version,
            )
        )
    )


@router.post("/jobs/{job_id}/schedule", status_code=202)
async def schedule(
    job_id: str,
    scope: RequestScope = Depends(request_scope),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if settings.social_control_plane_enabled:
        if not settings.social_mock_adapter_enabled:
            raise HTTPException(503, "social adapter disabled")
        repository = SocialRepository(db)
        job = await _async_call(
            lambda: repository.get_job(
                job_id, scope.organization_id, scope.workspace_id
            )
        )
        publications = await _async_call(
            lambda: repository.claim_publications(
                job_id,
                job["integration_ids"],
                scope.organization_id,
                scope.workspace_id,
            )
        )
        return {
            "content_job_id": job_id,
            "state": "queued",
            "provider_results": [
                {
                    "integration_id": item["integration_id"],
                    "state": item["state"],
                    "postly_group_id": item["postly_group_id"],
                }
                for item in publications
            ],
            "mock": True,
        }
    _mock_job(job_id, scope)
    return serialize_job(_call(lambda: control.schedule(job_id)))


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry(
    job_id: str,
    scope: RequestScope = Depends(request_scope),  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if settings.social_control_plane_enabled:
        raise HTTPException(409, "durable retries are worker-controlled")
    _mock_job(job_id, scope)
    return serialize_job(_call(lambda: control.retry(job_id)))


@router.post("/jobs/{job_id}/reconcile", status_code=202)
async def reconcile(
    job_id: str,
    scope: RequestScope = Depends(request_scope),  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if settings.social_control_plane_enabled:
        raise HTTPException(409, "durable reconciliation is worker-controlled")
    _mock_job(job_id, scope)
    return serialize_job(_call(lambda: control.reconcile(job_id)))


@router.get("/jobs/{job_id}")
async def status(
    job_id: str,
    scope: RequestScope = Depends(request_scope),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if settings.social_control_plane_enabled:
        return await _async_call(
            lambda: SocialRepository(db).get_job(
                job_id, scope.organization_id, scope.workspace_id
            )
        )
    return serialize_job(_mock_job(job_id, scope))


@router.get("/jobs/{job_id}/analytics")
async def analytics(
    job_id: str,
    scope: RequestScope = Depends(request_scope),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if settings.social_control_plane_enabled:
        metrics = await _async_call(
            lambda: SocialRepository(db).get_analytics(
                job_id, scope.organization_id, scope.workspace_id
            )
        )
    else:
        _mock_job(job_id, scope)
        metrics = _call(lambda: control.analytics(job_id))
    return {
        "content_job_id": job_id,
        "metrics": metrics,
        "mock": True,
    }


@router.get("/jobs/{job_id}/audit")
async def audit(
    job_id: str,
    scope: RequestScope = Depends(request_scope),  # noqa: B008
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if settings.social_control_plane_enabled:
        return {
            "content_job_id": job_id,
            "items": await _async_call(
                lambda: SocialRepository(db).get_audit(
                    job_id, scope.organization_id, scope.workspace_id
                )
            ),
            "mock": True,
        }
    job = _mock_job(job_id, scope)
    return {
        "content_job_id": job_id,
        "items": [
            {
                "sequence": item.sequence,
                "action": item.action,
                "from_state": item.from_state,
                "to_state": item.to_state,
                "actor_ref": item.actor_ref,
                "occurred_at": item.occurred_at.isoformat(),
                "safe_details": item.safe_details,
            }
            for item in job.audit
        ],
        "mock": True,
    }


@router.post("/provider-events", status_code=202)
async def provider_event(
    request: Request,
    x_postly_timestamp: str = Header(alias="X-Postly-Timestamp"),
    x_postly_callback_id: UUID = Header(alias="X-Postly-Callback-ID"),  # noqa: B008
    x_postly_signature: str = Header(alias="X-Postly-Signature"),
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    """Accept a signed adapter callback; disabled unless every callback gate is set."""
    _guard()
    if not settings.postly_callback_enabled:
        SOCIAL_CALLBACKS.labels("disabled").inc()
        raise HTTPException(404, "provider callback unavailable")
    if not settings.social_control_plane_enabled or settings.postly_adapter_enabled:
        raise HTTPException(503, "provider callback safety gates not satisfied")
    if not _source_allowed(request):
        SOCIAL_CALLBACKS.labels("source_rejected").inc()
        raise HTTPException(403, "provider callback source rejected")
    raw = await request.body()
    try:
        timestamp = int(x_postly_timestamp)
    except ValueError as exc:
        SOCIAL_CALLBACKS.labels("timestamp_rejected").inc()
        raise HTTPException(401, "invalid callback timestamp") from exc
    if (
        abs(int(datetime.now(UTC).timestamp()) - timestamp)
        > settings.signature_ttl_seconds
    ):
        SOCIAL_CALLBACKS.labels("timestamp_rejected").inc()
        raise HTTPException(401, "stale callback timestamp")
    supplied = x_postly_signature.removeprefix("sha256=").lower()
    expected = hmac.new(
        _callback_secret(), x_postly_timestamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied):
        SOCIAL_CALLBACKS.labels("signature_rejected").inc()
        raise HTTPException(401, "invalid callback signature")
    try:
        body = ProviderCallback.model_validate_json(raw)
    except ValueError as exc:
        SOCIAL_CALLBACKS.labels("schema_rejected").inc()
        raise HTTPException(422, "invalid provider callback") from exc
    if body.callback_id != x_postly_callback_id:
        SOCIAL_CALLBACKS.labels("binding_rejected").inc()
        raise HTTPException(409, "callback identifier binding conflict")
    result = await _async_call(
        lambda: SocialRepository(db).accept_provider_callback(
            body.model_dump(), hashlib.sha256(raw).hexdigest()
        )
    )
    SOCIAL_CALLBACKS.labels(str(result["status"])).inc()
    return {**result, "callback_id": str(body.callback_id)}
