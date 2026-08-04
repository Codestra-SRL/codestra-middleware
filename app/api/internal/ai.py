from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.internal.ai_jobs import WorkerPrincipal, authenticate_worker
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
_lock = Lock()


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
    principal: WorkerPrincipal = Depends(authenticate_worker),
) -> str:
    return principal.service_id


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
