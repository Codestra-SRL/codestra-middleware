from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.recording.domain import RecordingConflict, RecordingNotFound
from app.recording.odoo import AcknowledgingOdooClient
from app.recording.service import RecordingService
from app.recording.security import (
    AuthenticationError,
    ExporterIdentity,
    MTLSAuthorizer,
    ReplayGuard,
)
from app.recording.storage import MemoryObjectStorage

router = APIRouter(prefix="/api/v1/recordings", tags=["recordings"])

# Runtime composition must replace both adapters. Defaults perform no network or file IO.
recording_service = RecordingService(MemoryObjectStorage(), AcknowledgingOdooClient())
exporter_authorizer = MTLSAuthorizer(
    {"codestra-recording-exporter-server-b": "staging"}
)
exporter_replay_guard = ReplayGuard()


def require_exporter_mtls(
    identity: Annotated[str, Header(alias="X-TLS-Client-Identity")] = "",
    environment: Annotated[str, Header(alias="X-Certificate-Environment")] = "",
    role: Annotated[str, Header(alias="X-Certificate-Role")] = "",
    audience: Annotated[str, Header(alias="X-Audience")] = "",
    not_after: Annotated[str, Header(alias="X-TLS-Client-Not-After")] = "",
    revoked: Annotated[str, Header(alias="X-TLS-Client-Revoked")] = "true",
    nonce: Annotated[str, Header(alias="X-Request-Nonce")] = "",
    timestamp: Annotated[str, Header(alias="X-Request-Timestamp")] = "",
) -> None:
    try:
        expiry = datetime.fromisoformat(not_after.replace("Z", "+00:00"))
        exporter_authorizer.authorize(
            ExporterIdentity(
                identity, environment, role, audience, expiry, revoked != "false"
            )
        )
        exporter_replay_guard.consume(nonce, int(timestamp))
    except (AuthenticationError, ValueError, TypeError) as exc:
        raise HTTPException(401, "exporter mTLS binding rejected") from exc


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReservationRecording(StrictModel):
    contract_version: Literal["1.0"]
    vicidial_recording_id: str = Field(pattern=r"^[0-9]+$")
    vicidial_call_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    asterisk_uniqueid: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    campaign_key: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    agent_key: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    started_at: str
    duration_seconds: float = Field(ge=0)
    format: Literal["mp3", "wav", "gsm"]
    codec: str = Field(pattern=r"^[A-Za-z0-9._-]{1,32}$")
    channels: int = Field(ge=1, le=2)
    sample_rate_hz: int = Field(ge=8000, le=192000)
    file_size_bytes: int = Field(gt=0, le=5_000_000_000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment: Literal["staging", "production"]
    retention_class: Literal[
        "synthetic_test", "standard", "high_compliance", "legal_hold"
    ]


class ReservationRequest(StrictModel):
    contract_version: Literal["1.0"]
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    recording: ReservationRecording


class CompletionRequest(StrictModel):
    contract_version: Literal["1.0"]
    recording_uid: str = Field(pattern=r"^REC-[0-9a-f]{32}$")
    idempotency_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    environment: Literal["staging", "production"]
    campaign_key: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    file_size_bytes: int = Field(gt=0)
    format: Literal["mp3", "wav", "gsm"]
    duration_seconds: float = Field(ge=0)


class FailureRequest(StrictModel):
    code: str = Field(min_length=1, max_length=64)


class PlaybackRequest(StrictModel):
    requester_type: Literal["odoo", "approved_application"]
    user_level: int = Field(ge=8, le=9)
    campaign_authorized: bool
    group_authorized: bool
    ttl_seconds: int = Field(default=120, ge=1, le=120)


class AutomationResultRequest(StrictModel):
    idempotency_key: str = Field(min_length=16, max_length=255)
    result: dict[str, object]


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, RecordingNotFound):
        return HTTPException(404, "recording not found")
    if isinstance(exc, PermissionError):
        return HTTPException(403, str(exc))
    return HTTPException(409, str(exc))


@router.post("/reservations", status_code=201, dependencies=[Depends(require_exporter_mtls)])
async def reserve(payload: ReservationRequest):
    return recording_service.reserve(payload.model_dump())


@router.post("/{recording_uid}/complete", dependencies=[Depends(require_exporter_mtls)])
async def complete(recording_uid: str, payload: CompletionRequest):
    try:
        if payload.recording_uid != recording_uid:
            raise RecordingConflict("path and payload recording_uid differ")
        return await recording_service.complete(recording_uid, payload.model_dump())
    except (RecordingConflict, RecordingNotFound, KeyError, OSError) as exc:
        raise _translate(exc) from exc


@router.post("/{recording_uid}/failure", dependencies=[Depends(require_exporter_mtls)])
async def failure(recording_uid: str, payload: FailureRequest):
    try:
        return recording_service.failure(recording_uid, payload.code)
    except RecordingNotFound as exc:
        raise _translate(exc) from exc


@router.get("/{recording_uid}")
async def status(recording_uid: str):
    try:
        recording = recording_service.get(recording_uid)
    except RecordingNotFound as exc:
        raise _translate(exc) from exc
    return {
        "contract_version": "1.0",
        "recording_uid": recording.recording_uid,
        "state": recording.state.value,
        "checksum_verified": recording.verified_at is not None,
        "odoo_linked": recording.odoo_linked_at is not None,
        "failure_code": recording.failure_code,
    }


@router.post("/{recording_uid}/playback-url")
async def playback_url(
    recording_uid: str,
    payload: PlaybackRequest,
    response: Response,
    service_identity: str = Header(default="", alias="X-Service-Identity"),
):
    authorized_service = service_identity in {
        "codestra-odoo",
        "codestra-approved-recording-application",
    }
    scope = authorized_service and payload.campaign_authorized and (
        payload.user_level == 9 or payload.group_authorized
    )
    try:
        body = recording_service.playback_url(
            recording_uid,
            scope_authorized=scope,
            ttl_seconds=payload.ttl_seconds,
        )
    except (RecordingNotFound, PermissionError) as exc:
        raise _translate(exc) from exc
    response.headers["Cache-Control"] = "no-store"
    return body


@router.post("/{recording_uid}/automation-result")
async def automation_result(recording_uid: str, payload: AutomationResultRequest):
    try:
        return recording_service.automation_result(
            recording_uid, payload.idempotency_key, payload.result
        )
    except (RecordingConflict, RecordingNotFound) as exc:
        raise _translate(exc) from exc
