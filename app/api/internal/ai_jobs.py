"""Private polling contract for the outbound-only Qwen worker."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import base64
import binascii
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.x509.oid import ExtendedKeyUsageOID
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ai_jobs
from app.core.config import settings
from app.db.session import get_session

router = APIRouter(prefix="/internal/api/v1/ai", tags=["internal-ai-worker"])
HEX_64 = re.compile(r"[0-9a-f]{64}")
DECIMAL_TIMESTAMP = re.compile(r"[0-9]{10,11}")
SAFE_NONCE = re.compile(r"[A-Za-z0-9._~-]{16,128}")

SERVER_SCOPES = frozenset({
    "ai.auth.verify/read-only",
    "ai.worker.claim",
    "ai.worker.heartbeat",
    "ai.worker.chunks",
    "ai.worker.complete",
    "ai.worker.fail",
    "ai.worker.cancellation-check",
    "ai.worker.recover-expired",
})


@dataclass(frozen=True)
class WorkerPrincipal:
    service_id: str
    scopes: frozenset[str]


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


def _certificate_identity(encoded_certificate: str) -> None:
    try:
        certificate = x509.load_der_x509_certificate(
            base64.b64decode(encoded_certificate, validate=True)
        )
        ca_path = Path(settings.ai_worker_client_ca_file)
        if not ca_path.is_absolute() or ca_path.is_symlink() or not ca_path.is_file():
            raise ValueError("CA")
        authority = x509.load_pem_x509_certificate(ca_path.read_bytes())
        certificate.verify_directly_issued_by(authority)
        now = datetime.now(timezone.utc)
        if certificate.serial_number != int(settings.ai_worker_certificate_serial):
            raise ValueError("serial")
        if not (certificate.not_valid_before_utc <= now <= certificate.not_valid_after_utc):
            raise ValueError("validity")
        uris = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value.get_values_for_type(x509.UniformResourceIdentifier)
        if uris != [settings.ai_worker_spiffe_id]:
            raise ValueError("SPIFFE")
        addresses = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value.get_values_for_type(x509.IPAddress)
        if addresses != [ipaddress.ip_address(settings.ai_worker_certificate_ip)]:
            raise ValueError("IP SAN")
        usage = certificate.extensions.get_extension_for_class(x509.KeyUsage).value
        if not usage.digital_signature:
            raise ValueError("key usage")
        extended = certificate.extensions.get_extension_for_class(
            x509.ExtendedKeyUsage
        ).value
        if ExtendedKeyUsageOID.CLIENT_AUTH not in extended:
            raise ValueError("client auth")
    except (
        InvalidSignature,
        ValueError,
        UnicodeError,
        binascii.Error,
        x509.ExtensionNotFound,
    ) as exc:
        raise HTTPException(401, "authentication denied") from exc


async def _claim_nonce(
    db: AsyncSession, service_id: str, nonce: str, correlation_id: str
) -> None:
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(nonce.encode("ascii")).hexdigest()
    await db.execute(text("DELETE FROM ai_service_nonces WHERE expires_at <= now()"))
    result = await db.execute(text("""
        INSERT INTO ai_service_nonces
          (service_id, nonce_digest, received_at, expires_at, correlation_id)
        VALUES (:service, :digest, :received, :expires, :correlation)
        ON CONFLICT(service_id, nonce_digest) DO NOTHING
        RETURNING nonce_digest
    """), {
        "service": service_id,
        "digest": digest,
        "received": now,
        "expires": now + timedelta(seconds=settings.ai_signature_ttl_seconds),
        "correlation": correlation_id,
    })
    if result.scalar_one_or_none() is None:
        await db.rollback()
        raise HTTPException(409, "replay detected")
    await db.commit()


async def authenticate_worker(
    request: Request,
    service_id: Annotated[str, Header(alias="X-Service-ID")],
    hmac_key_id: Annotated[str, Header(alias="X-HMAC-Key-ID")],
    timestamp: Annotated[str, Header(alias="X-Timestamp")],
    nonce: Annotated[str, Header(alias="X-Nonce", min_length=16, max_length=128)],
    body_digest: Annotated[str, Header(alias="X-Body-SHA256")],
    signature: Annotated[str, Header(alias="X-Signature", min_length=64, max_length=64)],
    certificate: Annotated[
        str, Header(alias="X-Codestra-Client-Certificate-DER")
    ],
    source_ip: Annotated[str, Header(alias="X-Codestra-Source-IP")],
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=8, max_length=128)],
    db: AsyncSession = Depends(get_session),
) -> WorkerPrincipal:
    try:
        proxy = ipaddress.ip_address(request.client.host if request.client else "")
        trusted_proxy = ipaddress.ip_network(settings.ai_worker_trusted_proxy_cidr, strict=True)
    except ValueError as exc:
        raise HTTPException(404, "not found") from exc
    if proxy not in trusted_proxy or not _source_allowed(source_ip):
        raise HTTPException(404, "not found")
    _certificate_identity(certificate)
    if (service_id != settings.ai_worker_service_id
            or hmac_key_id != settings.ai_worker_hmac_key_id):
        raise HTTPException(403, "worker identity denied")
    if not DECIMAL_TIMESTAMP.fullmatch(timestamp) or not SAFE_NONCE.fullmatch(nonce):
        raise HTTPException(401, "authentication denied")
    signed_at = int(timestamp)
    now = time.time()
    if abs(now - signed_at) > settings.ai_signature_ttl_seconds:
        raise HTTPException(401, "authentication denied")
    secret_path = Path(settings.ai_hmac_secret_file)
    if not secret_path.is_absolute() or not secret_path.is_file():
        raise HTTPException(503, "worker authentication unavailable")
    secret = secret_path.read_bytes().strip()
    if not re.fullmatch(rb"[0-9a-fA-F]{64}", secret):
        raise HTTPException(503, "worker authentication unavailable")
    body = await request.body()
    digest = hashlib.sha256(body).hexdigest()
    if not HEX_64.fullmatch(body_digest) or not hmac.compare_digest(digest, body_digest):
        raise HTTPException(401, "authentication denied")
    canonical = "\n".join((request.method.upper(), request.url.path, service_id,
                            timestamp, nonce, body_digest))
    expected = hmac.new(secret, canonical.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise HTTPException(401, "authentication denied")
    await _claim_nonce(db, service_id, nonce, correlation_id)
    return WorkerPrincipal(
        service_id=settings.ai_worker_service_id,
        scopes=SERVER_SCOPES,
    )


def require_scope(scope: str):
    async def dependency(
        principal: WorkerPrincipal = Depends(authenticate_worker),
    ) -> WorkerPrincipal:
        if scope not in principal.scopes:
            raise HTTPException(403, "worker scope denied")
        return principal
    return dependency


def correlation(value: Annotated[str, Header(alias="X-Correlation-ID")]) -> str:
    if not 1 <= len(value) <= 128:
        raise HTTPException(400, "invalid correlation ID")
    return value


@router.post("/auth/verify")
async def verify_identity(_: WorkerPrincipal = Depends(require_scope("ai.auth.verify/read-only"))) -> dict[str, object]:
    return {"verified": True, "service": settings.ai_worker_service_id,
            "scope": "ai.auth.verify/read-only", "version": "1.0"}


@router.post("/worker/jobs/claim")
async def claim_job(body: LeaseRequest, _: WorkerPrincipal = Depends(require_scope("ai.worker.claim")),
                    request_id: str = Depends(correlation),
                    db: AsyncSession = Depends(get_session)) -> dict[str, object]:
    item = await ai_jobs.claim(db, body.worker_id, settings.ai_job_lease_seconds, request_id)
    return {"job": item}


@router.post("/worker/jobs/{job_id}/heartbeat")
async def job_heartbeat(job_id: UUID, body: LeaseMutation,
                        principal: WorkerPrincipal = Depends(require_scope("ai.worker.heartbeat")),
                        db: AsyncSession = Depends(get_session)) -> dict[str, object]:
    try:
        expires = await ai_jobs.heartbeat(
            db,
            job_id,
            body.worker_id,
            body.fencing_token,
            settings.ai_job_lease_seconds,
            service_id=principal.service_id,
            certificate_serial=settings.ai_worker_certificate_serial,
            spiffe_id=settings.ai_worker_spiffe_id,
        )
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"accepted": True, "lease_expires_at": expires}


@router.post("/worker/jobs/{job_id}/chunks")
async def job_chunk(job_id: UUID, body: ChunkRequest,
                    _: WorkerPrincipal = Depends(require_scope("ai.worker.chunks")),
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
                       _: WorkerPrincipal = Depends(require_scope("ai.worker.complete")),
                       request_id: str = Depends(correlation),
                       db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    return await _finish(job_id, body, False, None, False, request_id, db)


@router.post("/worker/jobs/{job_id}/fail")
async def fail_job(job_id: UUID, body: FailureRequest,
                   _: WorkerPrincipal = Depends(require_scope("ai.worker.fail")),
                   request_id: str = Depends(correlation),
                   db: AsyncSession = Depends(get_session)) -> dict[str, str]:
    return await _finish(job_id, body, True, body.error_code, body.retryable,
                         request_id, db)


@router.post("/worker/jobs/{job_id}/cancellation-check")
async def cancellation_check(job_id: UUID, body: LeaseMutation,
                             _: WorkerPrincipal = Depends(require_scope("ai.worker.cancellation-check")),
                             db: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    try:
        row = await ai_jobs.assert_lease(db, job_id, body.worker_id, body.fencing_token)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"cancel_requested": row["cancel_requested_at"] is not None}


@router.post("/worker/recover-expired")
async def recover(_: WorkerPrincipal = Depends(require_scope("ai.worker.recover-expired")),
                  db: AsyncSession = Depends(get_session)) -> dict[str, int]:
    return await ai_jobs.recover_expired(db)
