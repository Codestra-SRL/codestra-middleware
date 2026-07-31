from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.recordings import RecordingService

router = APIRouter(prefix="/api/v1/recordings", tags=["recordings"])
service: RecordingService | None = None


class Reservation(BaseModel):
    recording_uid: str = Field(pattern=r"^REC-[0-9a-f]{32}$")
    idempotency_key: str = Field(min_length=32, max_length=128)
    environment: str
    campaign_id: str = Field(min_length=1, max_length=64)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    content_type: str = Field(pattern=r"^audio/(mpeg|wav|ogg|gsm)$")
    vicidial_recording_id: str = Field(min_length=1, max_length=64)
    vicidial_call_id: str = Field(min_length=1, max_length=128)
    asterisk_uniqueid: str = Field(min_length=1, max_length=128)
    duration_seconds: float = Field(ge=0)
    format: str = Field(pattern=r"^(mp3|wav|gsm)$")
    codec: str = Field(min_length=1, max_length=32)
    channels: int = Field(ge=1, le=2)
    sample_rate_hz: int = Field(ge=8000, le=192000)


class Completion(BaseModel):
    environment: str
    campaign_id: str
    idempotency_key: str = Field(min_length=32, max_length=128)
    duration_seconds: float = Field(ge=0)
    format: str = Field(pattern=r"^(mp3|wav|gsm)$")


def configured() -> RecordingService:
    if service is None:
        raise HTTPException(503, "recording storage is not configured")
    return service


@router.post("/reservations")
def reserve(
    body: Reservation,
    x_verified_mtls_client_id: str = Header(default=""),
):
    try:
        return configured().reserve(body.model_dump(), x_verified_mtls_client_id)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/{recording_uid}/complete")
def complete(recording_uid: str, body: Completion,
             x_verified_mtls_client_id: str = Header(default="")):
    try:
        return configured().complete(
            recording_uid, body.model_dump(), x_verified_mtls_client_id
        )
    except (PermissionError, ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{recording_uid}/failure")
def failure(recording_uid: str, code: str,
            x_verified_mtls_client_id: str = Header(default="")):
    try:
        return configured().failure(recording_uid, code, x_verified_mtls_client_id)
    except (PermissionError, KeyError) as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/{recording_uid}")
def status(
    recording_uid: str,
    x_verified_mtls_client_id: str = Header(default=""),
):
    try:
        return configured().status(recording_uid, x_verified_mtls_client_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, "recording not found") from exc


@router.post("/{recording_uid}/playback-url")
def playback(
    recording_uid: str,
    x_verified_mtls_client_id: str = Header(default=""),
    x_recording_scope_authorized: str = Header(default="no"),
):
    try:
        if x_verified_mtls_client_id != "odoo-recording-service":
            raise PermissionError("untrusted mTLS service identity")
        return configured().playback(
            recording_uid, x_recording_scope_authorized.lower() == "yes"
        )
    except (PermissionError, KeyError) as exc:
        raise HTTPException(403, str(exc)) from exc
