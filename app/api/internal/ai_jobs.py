"""Private polling contract for the outbound-only Qwen worker."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ai_jobs
from app.core.config import settings
from app.db.session import get_session

router = APIRouter(prefix="/internal/api/v1/ai", tags=["internal-ai-worker"])
_nonces: dict[tuple[str, str], float] = {}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LeaseRequest(StrictModel):
    worker_id: str = Field(min_length=3, max_length=128)


class LeaseMutation(StrictModel):
    worker_id: str = Field(min_length=3, max_length=128)
    fencing_token: int = Field(ge=1)


class ChunkRequest(LeaseMutation):
    sequence: int = Field(ge=0)
    content: str = Field(min_length=1)


class FailureRequest(LeaseMutation):
    error_code: str = Field(pattern=r"^[a-z0-9_.-]{1,64}$")
    retryable: bool = False


def _source_allowed(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
        return any(address in ipaddress.ip_network(item.strip(), strict=False)
                   for item in settings.ai_worker_source_cidrs.split(",") if item.strip())
    except ValueError:
        return False


async def authenticate_worker(
    request: Request,
    service_id: Annotated[str, Header(alias="X-Service-ID")],
    timestamp: Annotated[str, Header(alias="X-Timestamp")],
    nonce: Annotated[str, Header(alias="X-Nonce", min_length=16, max_length=128)],
    signature: Annotated[str, Header(alias="X-Signature", min_length=64, max_length=64)],
    certificate_serial: Annotated[str, Header(alias="X-Client-Certificate-Serial")],
    spiffe_id: Annotated[str, Header(alias="X-Client-SPIFFE-ID")],
    scopes: Annotated[str, Header(alias="X-Service-Scopes")],
) -> str:
    if not _source_allowed(request.client.host if request.client else ""):
        raise HTTPException(404, "not found")
    required = set(settings.ai_worker_required_scopes.split())
    if (service_id != settings.ai_worker_service_id
            or certificate_serial != settings.ai_worker_certificate_serial
            or spiffe_id != settings.ai_worker_spiffe_id
            or not required.issubset(set(scopes.split()))):
        raise HTTPException(403, "worker identity denied")
    try:
        signed_at = int(timestamp)
    except ValueError as exc:
        raise HTTPException(401, "authentication denied") from exc
    now = time.time()
    if abs(now - signed_at) > settings.ai_signature_ttl_seconds:
        raise HTTPException(401, "authentication denied")
    secret_path = Path(settings.ai_hmac_secret_file)
    if not secret_path.is_absolute() or not secret_path.is_file():
        raise HTTPException(503, "worker authentication unavailable")
    secret = secret_path.read_bytes().strip()
    if len(secret) < 32:
        raise HTTPException(503, "worker authentication unavailable")
    body = await request.body()
    digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join((request.method, request.url.path, service_id, timestamp,
                            nonce, certificate_serial, spiffe_id, scopes, digest))
    expected = hmac.new(secret, canonical.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise HTTPException(401, "authentication denied")
    expired = [key for key, expiry in _nonces.items() if expiry <= now]
    for key in expired:
        del _nonces[key]
    key = (service_id, nonce)
    if key in _nonces:
        raise HTTPException(409, "replay detected")
    _nonces[key] = now + settings.ai_signature_ttl_seconds
    return service_id


def correlation(value: Annotated[str, Header(alias="X-Correlation-ID")]) -> str:
    if not 1 <= len(value) <= 128:
        raise HTTPException(400, "invalid correlation ID")
    return value


@router.post("/auth/verify")
async def verify_identity(_: str = Depends(authenticate_worker)) -> dict[str, object]:
    return {"verified": True, "service": settings.ai_worker_service_id,
            "scopes": settings.ai_worker_required_scopes.split(), "version": "1.0"}


@router.post("/worker/jobs/claim")
async def claim_job(body: LeaseRequest, _: str = Depends(authenticate_worker),
                    request_id: str = Depends(correlation),
                    db: AsyncSession = Depends(get_session)) -> dict[str, object]:
    item = await ai_jobs.claim(db, body.worker_id, settings.ai_job_lease_seconds, request_id)
    return {"job": item}


@router.post("/worker/jobs/{job_id}/heartbeat")
async def job_heartbeat(job_id: UUID, body: LeaseMutation,
                        _: str = Depends(authenticate_worker),
                        db: AsyncSession = Depends(get_session)) -> dict[str, object]:
    try:
        expires = await ai_jobs.heartbeat(db, job_id, body.worker_id,
                                          body.fencing_token, settings.ai_job_lease_seconds)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"accepted": True, "lease_expires_at": expires}


@router.post("/worker/jobs/{job_id}/chunks")
async def job_chunk(job_id: UUID, body: ChunkRequest,
                    _: str = Depends(authenticate_worker),
                    db: AsyncSession = Depends(get_session)) -> dict[str, object]:
    try:
        inserted = await ai_jobs.append_chunk(db, job_id, body.worker_id,
            body.fencing_token, body.sequence, body.content, settings.ai_job_max_output_bytes)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OverflowError as exc:
        raise HTTPException(413, str(exc)) from exc
    return {"accepted": True, "duplicate": not inserted}


async def _finish(job_id: UUID, body: LeaseMutation, failed: bool,
                  error_code: str | None, retryable: bool, request_id: str,
                  db: AsyncSession) -> dict[str, str]:
    try:
        state = await ai_jobs.finish(db, job_id, body.worker_id, body.fencing_token,
            failed=failed, error_code=error_code, retryable=retryable,
            correlation_id=request_id)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"state": state}


@router.post("/worker/jobs/{job_id}/complete")
async def complete_job(job_id: UUID, body: LeaseMutation,
                       _: str = Depends(authenticate_worker),
                       request_id: str = Depends(correlation),
                       db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    return await _finish(job_id, body, False, None, False, request_id, db)


@router.post("/worker/jobs/{job_id}/fail")
async def fail_job(job_id: UUID, body: FailureRequest,
                   _: str = Depends(authenticate_worker),
                   request_id: str = Depends(correlation),
                   db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    return await _finish(job_id, body, True, body.error_code, body.retryable,
                         request_id, db)


@router.post("/worker/jobs/{job_id}/cancellation-check")
async def cancellation_check(job_id: UUID, body: LeaseMutation,
                             _: str = Depends(authenticate_worker),
                             db: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    try:
        row = await ai_jobs.assert_lease(db, job_id, body.worker_id, body.fencing_token)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"cancel_requested": row["cancel_requested_at"] is not None}


@router.post("/worker/recover-expired")
async def recover(_: str = Depends(authenticate_worker),
                  db: AsyncSession = Depends(get_session)) -> dict[str, int]:
    return await ai_jobs.recover_expired(db)
