from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

PREFIX = "/internal/api/v1/ai"
router = APIRouter(prefix=PREFIX, tags=["internal-ai"])


class Target(str, Enum):
    ODOO = "odoo"
    N8N = "n8n"
    VICIDIAL = "vicidial"
    POSTLY = "postly"


class Action(str, Enum):
    ODOO_LOOKUP = "odoo.lookup"
    N8N_INSPECT = "n8n.inspect"
    VICIDIAL_INSPECT = "vicidial.inspect"
    POSTLY_INSPECT = "postly.inspect"


ACTION_TARGET = {
    Action.ODOO_LOOKUP: Target.ODOO,
    Action.N8N_INSPECT: Target.N8N,
    Action.VICIDIAL_INSPECT: Target.VICIDIAL,
    Action.POSTLY_INSPECT: Target.POSTLY,
}


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Action
    target: Target
    arguments: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=5, ge=1, le=10)


class CallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    event: Literal["accepted", "progress", "completed", "failed"]
    data: dict[str, Any] = Field(default_factory=dict)


class MockAdapter:
    def __init__(self, target: Target):
        self.target = target

    async def execute(self, action: Action, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"adapter": f"mock:{self.target}", "action": action, "arguments": arguments,
                "downstream_contacted": False, "writes_performed": False}


ADAPTERS = {target: MockAdapter(target) for target in Target}
_commands: dict[str, dict[str, Any]] = {}
_idempotency: dict[tuple[str, str], tuple[str, str]] = {}
_callback_idempotency: dict[tuple[str, str], str] = {}
_nonces: dict[tuple[str, str], float] = {}
_rate: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _secret() -> bytes:
    path = Path(settings.ai_hmac_secret_file)
    if not settings.ai_hmac_secret_file or not path.is_absolute() or not path.is_file():
        raise HTTPException(503, "AI service authentication is not configured")
    value = path.read_bytes().strip()
    if len(value) < 32:
        raise HTTPException(503, "AI service authentication is not configured")
    return value


def _audit(event: str, **fields: Any) -> None:
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event, **fields}
    if settings.ai_audit_log_file:
        path = Path(settings.ai_audit_log_file)
        if not path.is_absolute():
            raise HTTPException(503, "AI audit path must be absolute")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


async def authenticate(
    request: Request,
    x_service_id: str = Header(alias="X-Service-ID"),
    x_timestamp: str = Header(alias="X-Timestamp"),
    x_nonce: str = Header(alias="X-Nonce", min_length=16, max_length=128),
    x_signature: str = Header(alias="X-Signature", min_length=64, max_length=64),
) -> str:
    now = time.time()
    try:
        timestamp = int(x_timestamp)
    except ValueError as exc:
        raise HTTPException(401, "invalid timestamp") from exc
    if x_service_id != settings.ai_service_id or abs(now - timestamp) > settings.ai_signature_ttl_seconds:
        _audit("authentication.denied", service_id=x_service_id, reason="identity_or_timestamp")
        raise HTTPException(401, "authentication denied")
    body = await request.body()
    digest = hashlib.sha256(body).hexdigest()
    canonical = "\n".join((request.method, request.url.path, x_service_id, x_timestamp, x_nonce, digest))
    expected = hmac.new(_secret(), canonical.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_signature.lower()):
        _audit("authentication.denied", service_id=x_service_id, reason="signature")
        raise HTTPException(401, "authentication denied")
    with _lock:
        expired = [key for key, expiry in _nonces.items() if expiry <= now]
        for key in expired:
            del _nonces[key]
        nonce_key = (x_service_id, x_nonce)
        if nonce_key in _nonces:
            _audit("authentication.denied", service_id=x_service_id, reason="replay")
            raise HTTPException(409, "replay detected")
        _nonces[nonce_key] = now + settings.ai_signature_ttl_seconds
        bucket = _rate[x_service_id]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= settings.ai_rate_limit_per_minute:
            raise HTTPException(429, "rate limit exceeded")
        bucket.append(now)
    request.state.ai_service_id = x_service_id
    _audit("authentication.accepted", service_id=x_service_id, method=request.method,
           path=request.url.path, body_hash=digest)
    return x_service_id


def _context(correlation_id: str | None, idempotency_key: str | None) -> tuple[str, str]:
    if not correlation_id or len(correlation_id) > 128:
        raise HTTPException(400, "X-Correlation-ID is required")
    if not idempotency_key or not 16 <= len(idempotency_key) <= 255:
        raise HTTPException(400, "Idempotency-Key is required")
    return correlation_id, idempotency_key


@router.get("/health")
async def health(_: str = Depends(authenticate)) -> dict[str, Any]:
    return {"status": "ok", "mode": "mock-only", "private_api_enabled": settings.ai_private_api_enabled,
            "production_writes": "disabled"}


@router.get("/capabilities")
async def capabilities(_: str = Depends(authenticate)) -> dict[str, Any]:
    return {"commands": [value for value in Action], "targets": [value for value in Target],
            "adapters": "mock-only", "authorization": "deny-by-default",
            "downstream_credentials_exposed": False, "max_timeout_seconds": 10}


@router.post("/commands", status_code=status.HTTP_202_ACCEPTED)
async def create_command(
    body: CommandRequest,
    service_id: str = Depends(authenticate),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    correlation_id, idempotency_key = _context(correlation_id, idempotency_key)
    if not settings.ai_private_api_enabled:
        raise HTTPException(503, "private AI API disabled")
    if ACTION_TARGET.get(body.action) != body.target:
        _audit("authorization.denied", service_id=service_id, correlation_id=correlation_id,
               target=body.target, action=body.action)
        raise HTTPException(403, "action is not authorized for target")
    request_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    key = (service_id, idempotency_key)
    with _lock:
        existing = _idempotency.get(key)
        if existing:
            command_id, old_hash = existing
            if old_hash != request_hash:
                raise HTTPException(409, "idempotency key conflict")
            _audit("command.idempotent_replay", service_id=service_id, command_id=command_id,
                   correlation_id=correlation_id)
            return {**_commands[command_id], "idempotent_replay": True}
    command_id = str(uuid4())
    try:
        result = await asyncio.wait_for(
            ADAPTERS[body.target].execute(body.action, body.arguments),
            timeout=min(body.timeout_seconds, settings.ai_command_timeout_seconds),
        )
    except TimeoutError as exc:
        raise HTTPException(504, "mock command timed out") from exc
    record = {"command_id": command_id, "status": "completed_mock", "correlation_id": correlation_id,
              "target": body.target, "action": body.action, "result": result, "idempotent_replay": False}
    with _lock:
        _commands[command_id] = record
        _idempotency[key] = (command_id, request_hash)
    _audit("command.completed_mock", service_id=service_id, command_id=command_id,
           correlation_id=correlation_id, idempotency_key_hash=hashlib.sha256(idempotency_key.encode()).hexdigest(),
           request_hash=request_hash, target=body.target, action=body.action, outcome="completed_mock")
    return record


@router.get("/commands/{command_id}")
async def get_command(command_id: UUID, _: str = Depends(authenticate)) -> dict[str, Any]:
    record = _commands.get(str(command_id))
    if not record:
        raise HTTPException(404, "command not found")
    _audit("command.read", command_id=str(command_id), correlation_id=record["correlation_id"])
    return record


@router.post("/callbacks/qwen", status_code=status.HTTP_202_ACCEPTED)
async def qwen_callback(
    body: CallbackRequest,
    service_id: str = Depends(authenticate),
    correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    correlation_id, idempotency_key = _context(correlation_id, idempotency_key)
    if str(body.command_id) not in _commands:
        raise HTTPException(404, "command not found")
    payload_hash = hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    key = (service_id, idempotency_key)
    with _lock:
        previous_hash = _callback_idempotency.get(key)
        if previous_hash and previous_hash != payload_hash:
            raise HTTPException(409, "idempotency key conflict")
        duplicate = previous_hash is not None
        _callback_idempotency[key] = payload_hash
    _audit("qwen.callback.accepted", service_id=service_id, command_id=str(body.command_id),
           correlation_id=correlation_id, idempotency_key_hash=hashlib.sha256(idempotency_key.encode()).hexdigest(),
           callback_event=body.event, payload_hash=payload_hash, idempotent_replay=duplicate)
    return {"accepted": True, "dispatch_performed": False, "production_writes": False,
            "idempotent_replay": duplicate}
