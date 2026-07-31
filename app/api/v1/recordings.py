from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.recording.domain import RecordingConflict, RecordingNotFound
from app.recording.odoo import AcknowledgingOdooClient
from app.recording.service import RecordingService
from app.recording.storage import MemoryObjectStorage

router = APIRouter(prefix="/api/v1/recordings", tags=["recordings"])

# Runtime composition must replace both adapters. Defaults perform no network or file IO.
recording_service = RecordingService(MemoryObjectStorage(), AcknowledgingOdooClient())


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReservationRequest(StrictModel):
    environment: Literal["staging", "test", "production"]
    campaign_key: str = Field(min_length=1, max_length=128)
    call_uid: str = Field(min_length=1, max_length=144)
    idempotency_key: str = Field(min_length=16, max_length=255)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0, le=5_000_000_000)
    content_type: Literal["audio/mpeg", "audio/wav", "audio/gsm"]
    retention_class: Literal[
        "synthetic_test", "standard", "high_compliance", "legal_hold"
    ] = "standard"
    duration_seconds: float | None = Field(default=None, ge=0)


class CompletionRequest(StrictModel):
    object_version_id: str = Field(min_length=1, max_length=255)


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


@router.post("/reservations", status_code=201)
async def reserve(payload: ReservationRequest):
    return recording_service.reserve(payload.model_dump())


@router.post("/{recording_uid}/complete")
async def complete(recording_uid: str, payload: CompletionRequest):
    try:
        return await recording_service.complete(recording_uid, payload.model_dump())
    except (RecordingConflict, RecordingNotFound, KeyError, OSError) as exc:
        raise _translate(exc) from exc


@router.post("/{recording_uid}/failure")
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
        "recording_uid": recording.recording_uid,
        "environment": recording.environment,
        "campaign_key": recording.campaign_key,
        "call_uid": recording.call_uid,
        "state": recording.state.value,
        "checksum_verified": recording.verified_at is not None,
        "odoo_linked": recording.odoo_linked_at is not None,
        "retention_class": recording.retention_class,
        "legal_hold": recording.legal_hold,
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
