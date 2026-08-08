from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.config import settings
from app.core.sales_leads import (
    IdempotencyConflict,
    LeadCandidate,
    SalesLeadService,
    verify_scraper,
)

router = APIRouter(prefix="/api/v1/sales", tags=["sales-lead-foundation"])
service = SalesLeadService()
LEAD_REQUEST_DOC = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": LeadCandidate.model_json_schema()}},
    }
}
JOB_REQUEST_DOC = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "source",
                        "tenant_id",
                        "dry_run",
                        "write_changes",
                        "publish_to_vicidial",
                        "batch_size",
                    ],
                    "properties": {
                        "source": {"const": "odoo"},
                        "tenant_id": {"type": "string", "minLength": 1},
                        "campaign_id": {"type": ["string", "null"]},
                        "filters": {"type": "object"},
                        "dry_run": {"const": True},
                        "write_changes": {"const": False},
                        "publish_to_vicidial": {"const": False},
                        "batch_size": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                }
            }
        },
    }
}


def error(
    code: str, message: str, correlation_id: str, status: int, retryable: bool = False
) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "correlation_id": correlation_id or "generated",
                "retryable": retryable,
            }
        },
        status_code=status,
    )


def parse_candidate(raw: bytes, correlation_id: str) -> LeadCandidate | JSONResponse:
    if len(raw) > min(settings.request_max_bytes, 131072):
        return error(
            "REQUEST_TOO_LARGE",
            "request exceeds the bounded intake size",
            correlation_id,
            413,
        )
    try:
        return LeadCandidate.model_validate_json(raw)
    except (ValidationError, ValueError):
        return error(
            "LEAD_CANDIDATE_INVALID",
            "lead candidate validation failed",
            correlation_id,
            422,
        )


@router.post("/lead-candidates/validate", openapi_extra=LEAD_REQUEST_DOC)
async def validate_candidate(request: Request):
    correlation = request.headers.get("X-Correlation-ID", "generated")
    candidate = parse_candidate(await request.body(), correlation)
    if isinstance(candidate, JSONResponse):
        return candidate
    return {
        "valid": True,
        "schema_version": candidate.schema_version,
        "dry_run": True,
        "correlation_id": correlation,
    }


@router.post("/lead-candidates/resolve", openapi_extra=LEAD_REQUEST_DOC)
async def resolve_candidate(
    request: Request, idempotency_key: str = Header("", alias="Idempotency-Key")
):
    correlation = request.headers.get("X-Correlation-ID", "generated")
    if (
        not settings.sales_lead_intake_enabled
        or not settings.sales_identity_resolution_enabled
        or not settings.sales_odoo_read_only_lookup_enabled
    ):
        return error(
            "SALES_FEATURE_DISABLED",
            "sales lead resolution is disabled",
            correlation,
            503,
        )
    candidate = parse_candidate(await request.body(), correlation)
    if isinstance(candidate, JSONResponse):
        return candidate
    try:
        return service.resolve(candidate, idempotency_key)
    except IdempotencyConflict:
        return error(
            "IDEMPOTENCY_PAYLOAD_CONFLICT",
            "idempotency key was already used for a different payload",
            correlation,
            409,
        )
    except ValueError:
        return error(
            "LEAD_RESOLUTION_INVALID",
            "lead resolution request is invalid",
            correlation,
            422,
        )


@router.post("/verification-jobs", status_code=202, openapi_extra=JOB_REQUEST_DOC)
async def create_verification_job(
    request: Request, idempotency_key: str = Header("", alias="Idempotency-Key")
):
    correlation = request.headers.get("X-Correlation-ID", "generated")
    if not settings.sales_verification_jobs_enabled:
        return error(
            "SALES_FEATURE_DISABLED", "verification jobs are disabled", correlation, 503
        )
    try:
        body: dict[str, Any] = await request.json()
        job = service.create_job(body, idempotency_key)
    except IdempotencyConflict:
        return error(
            "IDEMPOTENCY_PAYLOAD_CONFLICT",
            "idempotency key was already used for a different payload",
            correlation,
            409,
        )
    except (ValueError, json.JSONDecodeError):
        return error(
            "DRY_RUN_JOB_INVALID",
            "Phase 1 jobs must be bounded dry runs",
            correlation,
            422,
        )
    return {
        "job_id": job.job_id,
        "state": job.state,
        "dry_run": True,
        "write_changes": False,
        "publish_to_vicidial": False,
    }


@router.get("/verification-jobs/{job_id}")
def get_verification_job(
    job_id: str, x_tenant_id: str = Header("", alias="X-Tenant-ID")
):
    job = service.jobs.get(job_id)
    if not job or job.tenant_id != x_tenant_id:
        return error(
            "JOB_NOT_FOUND", "verification job was not found", "generated", 404
        )
    return {
        "job_id": job.job_id,
        "state": job.state,
        "total": job.total,
        "processed": job.processed,
        "dry_run": True,
    }


@router.get("/verification-jobs/{job_id}/results")
def get_verification_results(
    job_id: str, x_tenant_id: str = Header("", alias="X-Tenant-ID")
):
    job = service.jobs.get(job_id)
    if not job or job.tenant_id != x_tenant_id:
        return error(
            "JOB_NOT_FOUND", "verification job was not found", "generated", 404
        )
    return {"job_id": job.job_id, "results": job.results}


@router.post("/scraper-results", openapi_extra=LEAD_REQUEST_DOC)
async def ingest_scraper_result(
    request: Request, idempotency_key: str = Header("", alias="Idempotency-Key")
):
    correlation = request.headers.get("X-Correlation-ID", "generated")
    if (
        request.headers.get("content-type", "").split(";", 1)[0].lower()
        != "application/json"
    ):
        return error(
            "INVALID_CONTENT_TYPE", "application/json is required", correlation, 415
        )
    raw = await request.body()
    if len(raw) > min(settings.request_max_bytes, 131072):
        return error(
            "REQUEST_TOO_LARGE",
            "request exceeds the bounded intake size",
            correlation,
            413,
        )
    if not settings.scraper_result_ingest_enabled or not settings.scraper_hmac_secret:
        return error(
            "SCRAPER_INGEST_DISABLED", "scraper ingestion is disabled", correlation, 503
        )
    headers = {
        key: request.headers.get(key, "")
        for key in (
            "X-Scraper-Identity",
            "X-Tenant-ID",
            "X-Campaign-ID",
            "X-Request-ID",
            "X-Codestra-Timestamp",
            "X-Codestra-Nonce",
            "X-Content-SHA256",
            "X-Signature-Version",
            "X-Codestra-Signature",
        )
    }
    try:
        verify_scraper(
            raw,
            headers,
            settings.scraper_hmac_secret.encode(),
            settings.scraper_identity,
            service.nonces,
        )
    except PermissionError as exc:
        return error(str(exc), "scraper authentication failed", correlation, 401)
    candidate = parse_candidate(raw, correlation)
    if isinstance(candidate, JSONResponse):
        return candidate
    if (
        candidate.tenant_id != headers["X-Tenant-ID"]
        or candidate.campaign_id != headers["X-Campaign-ID"]
        or candidate.source.request_id != headers["X-Request-ID"]
    ):
        return error(
            "WRONG_TENANT_BINDING",
            "scraper binding does not match payload",
            correlation,
            403,
        )
    try:
        return service.accept_scraper(candidate, idempotency_key)
    except IdempotencyConflict:
        return error(
            "IDEMPOTENCY_PAYLOAD_CONFLICT",
            "idempotency key was already used for a different payload",
            correlation,
            409,
        )
    except ValueError:
        return error(
            "LEAD_CANDIDATE_INVALID",
            "scraper idempotency binding is invalid",
            correlation,
            422,
        )
