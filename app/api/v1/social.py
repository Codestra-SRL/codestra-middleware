"""Mock-only social control-plane routes; no provider network writes."""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.social_postly import SocialControlPlane, SocialError, serialize_job
from app.core.social_repository import SocialRepository
from app.db.session import get_session

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
    body: JobRequest, db: AsyncSession = Depends(get_session)  # noqa: B008
) -> dict[str, Any]:
    _guard()
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
    execution_id: str = Header("", alias="X-N8N-Execution-ID"),
    db: AsyncSession = Depends(get_session),  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if settings.social_control_plane_enabled:
        if not execution_id:
            raise HTTPException(422, "n8n execution identifier required")
        return await _async_call(
            lambda: SocialRepository(db).store_proposal(
                job_id, body.model_dump(), execution_id
            )
        )
    return serialize_job(
        _call(lambda: control.accept_n8n_proposal(job_id, body.model_dump()))
    )


@router.post("/jobs/{job_id}/approve")
async def approve(
    job_id: str,
    body: ApprovalRequest,
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
            )
        )
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
    job_id: str, db: AsyncSession = Depends(get_session)  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if settings.social_control_plane_enabled:
        if not settings.social_mock_adapter_enabled:
            raise HTTPException(503, "social adapter disabled")
        repository = SocialRepository(db)
        job = await _async_call(lambda: repository.get_job(job_id))
        publications = await _async_call(
            lambda: repository.claim_publications(job_id, job["integration_ids"])
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
    return serialize_job(_call(lambda: control.schedule(job_id)))


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry(job_id: str) -> dict[str, Any]:
    _guard()
    return serialize_job(_call(lambda: control.retry(job_id)))


@router.post("/jobs/{job_id}/reconcile", status_code=202)
async def reconcile(job_id: str) -> dict[str, Any]:
    _guard()
    return serialize_job(_call(lambda: control.reconcile(job_id)))


@router.get("/jobs/{job_id}")
async def status(
    job_id: str, db: AsyncSession = Depends(get_session)  # noqa: B008
) -> dict[str, Any]:
    _guard()
    if settings.social_control_plane_enabled:
        return await _async_call(lambda: SocialRepository(db).get_job(job_id))
    return serialize_job(_call(lambda: control._get(job_id)))


@router.get("/jobs/{job_id}/analytics")
async def analytics(job_id: str) -> dict[str, Any]:
    _guard()
    return {
        "content_job_id": job_id,
        "metrics": _call(lambda: control.analytics(job_id)),
        "mock": True,
    }


@router.get("/jobs/{job_id}/audit")
async def audit(job_id: str) -> dict[str, Any]:
    _guard()
    job = _call(lambda: control._get(job_id))
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
