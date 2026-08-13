from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.config import settings
from app.sales.auth import (
    NonceLedger,
    ScraperAuthenticationError,
    ScraperIdentity,
    verify,
)
from app.sales.contracts import (
    LeadCandidate,
    LeadResolution,
    SafeError,
    VerificationJobRequest,
)
from app.sales.odoo import DisabledOdooReadOnlyAdapter
from app.sales.odoo import SyntheticCanaryOdooReadOnlyAdapter
from app.sales.repository import SalesRepository
from app.sales.service import SalesError, SalesLeadService


router = APIRouter(prefix="/api/v1/sales", tags=["sales-lead-foundation"])
service = SalesLeadService(
    SyntheticCanaryOdooReadOnlyAdapter()
    if settings.scraper_middleware_delivery_enabled
    else DisabledOdooReadOnlyAdapter()
)
repository: SalesRepository | None = SalesRepository()
scraper_nonces = NonceLedger()


def _correlation(request: Request) -> str:
    return request.headers.get("X-Correlation-ID", "").strip() or str(uuid4())


def _error(
    code: str, message: str, correlation_id: str, status: int, retryable: bool = False
) -> JSONResponse:
    body = SafeError(
        code=code, message=message, correlation_id=correlation_id, retryable=retryable
    )
    return JSONResponse(
        body.model_dump(mode="json"),
        status_code=status,
        headers={"X-Correlation-ID": correlation_id},
    )


def _disabled(correlation_id: str, flag: str) -> JSONResponse:
    return _error("FEATURE_DISABLED", f"{flag} is disabled", correlation_id, 503, False)


@router.post("/lead-candidates/validate")
async def validate_candidate(request: Request, candidate: LeadCandidate):
    correlation_id = _correlation(request)
    if not settings.sales_lead_intake_enabled:
        return _disabled(correlation_id, "SALES_LEAD_INTAKE_ENABLED")
    return {
        "valid": True,
        "schema_version": candidate.schema_version,
        "dry_run": True,
        "correlation_id": correlation_id,
    }


@router.post("/lead-candidates/resolve", response_model=LeadResolution)
async def resolve_candidate(
    request: Request,
    candidate: LeadCandidate,
    idempotency_key: str = Header("", alias="Idempotency-Key"),
):
    correlation_id = _correlation(request)
    if (
        not settings.sales_lead_intake_enabled
        or not settings.sales_identity_resolution_enabled
    ):
        return _disabled(correlation_id, "SALES_IDENTITY_RESOLUTION_ENABLED")
    try:
        result, replay = await (
            repository.resolve(candidate, idempotency_key, correlation_id, service)
            if repository
            else service.resolve(candidate, idempotency_key, correlation_id)
        )
    except SalesError as exc:
        return _error(
            exc.code,
            "lead resolution request was rejected",
            correlation_id,
            exc.status,
            exc.retryable,
        )
    headers = {
        "X-Correlation-ID": result.correlation_id,
        "X-Idempotent-Replay": str(replay).lower(),
    }
    return JSONResponse(
        result.model_dump(mode="json"), status_code=200, headers=headers
    )


@router.post("/scraper-results", response_model=LeadResolution)
async def scraper_results(
    request: Request, idempotency_key: str = Header("", alias="Idempotency-Key")
):
    correlation_id = _correlation(request)
    if not settings.scraper_result_ingest_enabled:
        return _disabled(correlation_id, "SCRAPER_RESULT_INGEST_ENABLED")
    raw = await request.body()
    if len(raw) > settings.sales_lead_request_max_bytes:
        return _error(
            "OVERSIZED_PAYLOAD",
            "request exceeds the scraper limit",
            correlation_id,
            413,
        )
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        return _error(
            "INVALID_CONTENT_TYPE", "application/json is required", correlation_id, 415
        )
    try:
        untrusted = json.loads(raw)
        tenant_id = str(untrusted["tenant_id"])
        campaign_id = str(untrusted["campaign_id"])
        request_id = str(untrusted["source"]["request_id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _error(
            "INVALID_LEAD_CANDIDATE",
            "lead candidate validation failed",
            correlation_id,
            422,
        )
    scraper_id = request.headers.get("X-Codestra-Scraper-ID", "")
    identity = None
    try:
        secret = settings.sales_scraper_hmac_secret
    except ValueError:
        secret = b""
    if secret and scraper_id == settings.sales_scraper_identity:
        identity = ScraperIdentity(
            scraper_id,
            settings.sales_scraper_tenant_id,
            frozenset(
                value.strip()
                for value in settings.sales_scraper_campaign_allowlist.split(",")
                if value.strip()
            ),
            secret,
        )
    try:
        verify(
            identity=identity,
            scraper_id=scraper_id,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            request_id=request_id,
            timestamp=request.headers.get("X-Codestra-Timestamp", ""),
            nonce=request.headers.get("X-Codestra-Nonce", ""),
            supplied_signature=request.headers.get("X-Codestra-Signature", ""),
            supplied_hash=request.headers.get("X-Codestra-Content-SHA256", ""),
            version=request.headers.get("X-Codestra-Signature-Version", ""),
            body=raw,
            nonces=scraper_nonces,
        )
    except ScraperAuthenticationError as exc:
        return _error(str(exc), "scraper authentication failed", correlation_id, 401)
    if repository:
        try:
            consumed = await repository.consume_scraper_nonce(
                scraper_id, tenant_id, request.headers.get("X-Codestra-Nonce", "")
            )
        except SalesError as exc:
            return _error(
                exc.code,
                "scraper replay protection is unavailable",
                correlation_id,
                exc.status,
                exc.retryable,
            )
        if not consumed:
            return _error(
                "REPLAYED_NONCE", "scraper authentication failed", correlation_id, 401
            )
    try:
        candidate = LeadCandidate.model_validate_json(raw)
        result, replay = await (
            repository.resolve(
                candidate,
                idempotency_key,
                correlation_id,
                service,
                source_identity=scraper_id,
                persist_scraper_inbox=True,
            )
            if repository
            else service.resolve(candidate, idempotency_key, correlation_id)
        )
    except ValidationError:
        return _error(
            "INVALID_LEAD_CANDIDATE",
            "lead candidate validation failed",
            correlation_id,
            422,
        )
    except SalesError as exc:
        return _error(
            exc.code,
            "scraper result was rejected",
            correlation_id,
            exc.status,
            exc.retryable,
        )
    return JSONResponse(
        result.model_dump(mode="json"),
        headers={
            "X-Correlation-ID": result.correlation_id,
            "X-Idempotent-Replay": str(replay).lower(),
        },
    )


@router.post("/verification-jobs")
async def create_verification_job(
    request: Request,
    body: VerificationJobRequest,
    idempotency_key: str = Header("", alias="Idempotency-Key"),
):
    correlation_id = _correlation(request)
    if not settings.sales_verification_jobs_enabled:
        return _disabled(correlation_id, "SALES_VERIFICATION_JOBS_ENABLED")
    try:
        job, replay = await service.create_job(body, idempotency_key, correlation_id)
        if repository and not replay:
            await repository.persist_job(job)
    except SalesError as exc:
        return _error(
            exc.code,
            "verification job was rejected",
            correlation_id,
            exc.status,
            exc.retryable,
        )
    return JSONResponse(
        service.job_document(job),
        status_code=202,
        headers={"X-Idempotent-Replay": str(replay).lower()},
    )


@router.get("/verification-jobs/{job_id}")
async def get_verification_job(
    job_id: str,
    request: Request,
    tenant_id: str = Header("", alias="X-Codestra-Tenant-ID"),
):
    correlation_id = _correlation(request)
    job = service.jobs.get(job_id)
    if not job or job.request.tenant_id != tenant_id:
        return _error(
            "VERIFICATION_JOB_NOT_FOUND",
            "verification job was not found",
            correlation_id,
            404,
        )
    return service.job_document(job)


@router.get("/verification-jobs/{job_id}/results")
async def get_verification_results(
    job_id: str,
    request: Request,
    tenant_id: str = Header("", alias="X-Codestra-Tenant-ID"),
):
    correlation_id = _correlation(request)
    job = service.jobs.get(job_id)
    if not job or job.request.tenant_id != tenant_id:
        return _error(
            "VERIFICATION_JOB_NOT_FOUND",
            "verification job was not found",
            correlation_id,
            404,
        )
    return service.job_document(job, include_results=True)


@router.post("/verification-jobs/{job_id}/cancel")
async def cancel_verification_job(
    job_id: str,
    request: Request,
    tenant_id: str = Header("", alias="X-Codestra-Tenant-ID"),
):
    correlation_id = _correlation(request)
    if not settings.sales_verification_jobs_enabled:
        return _disabled(correlation_id, "SALES_VERIFICATION_JOBS_ENABLED")
    try:
        job = service.cancel_job(job_id, tenant_id)
    except SalesError:
        return _error(
            "VERIFICATION_JOB_NOT_FOUND",
            "verification job was not found",
            correlation_id,
            404,
        )
    return service.job_document(job)
