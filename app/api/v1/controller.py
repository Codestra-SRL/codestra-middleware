"""Private restricted Controller API candidate."""

from functools import lru_cache
from pathlib import Path
from inspect import isawaitable
from typing import Any, Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.controller import ApprovalTokens, ControllerError, RestrictedController
from app.core.controller_repository import PostgresControllerRepository
from app.db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["private-controller"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskCreate(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=4000)
    workspace: str = Field(min_length=1, max_length=1024)


class PlanStep(StrictModel):
    tool: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


class PlanCreate(StrictModel):
    steps: list[PlanStep] = Field(min_length=1, max_length=64)


class Approval(StrictModel):
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    server_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")


class QueueTask(StrictModel):
    priority: int = Field(default=5, ge=0, le=9)
    timeout_seconds: int = Field(default=600, ge=1, le=3600)
    max_attempts: int = Field(default=3, ge=1, le=10)


class WorkerClaim(StrictModel):
    server_id: str = Field(pattern=r"^(middleware|web)$")
    worker_id: str = Field(min_length=3, max_length=128)
    lease_seconds: int = Field(default=60, ge=10, le=300)


class WorkerLease(StrictModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    server_id: str = Field(pattern=r"^(middleware|web)$")
    worker_id: str = Field(min_length=3, max_length=128)
    expected_version: int = Field(ge=1)
    lease_seconds: int = Field(default=60, ge=10, le=300)


class WorkerFinish(StrictModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    server_id: str = Field(pattern=r"^(middleware|web)$")
    worker_id: str = Field(min_length=3, max_length=128)
    expected_version: int = Field(ge=1)
    evidence: dict[str, Any]


class WorkerFail(StrictModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    server_id: str = Field(pattern=r"^(middleware|web)$")
    worker_id: str = Field(min_length=3, max_length=128)
    expected_version: int = Field(ge=1)
    error_code: str = Field(min_length=1, max_length=64)
    retryable: bool


class ExecutionCreate(StrictModel):
    task_id: str
    server_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    workspace: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    approval_token: str


class AgentRegistration(StrictModel):
    server_id: str = Field(pattern=r"^(middleware|qwen|web|vici)$")
    spiffe_id: str
    private_endpoint: str
    profile: str = Field(pattern=r"^(DEVELOPMENT|PRODUCTION_OBSERVER)$")
    certificate_sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    certificate_serial: str = Field(min_length=1, max_length=128)
    not_after: str = Field(min_length=20, max_length=40)
    rotation_owner: str = Field(min_length=1, max_length=128)
    public_listener: bool = False


def _required(value: str, name: str) -> str:
    if not value.strip():
        raise HTTPException(422, f"{name} is required")
    return value


Tenant = Annotated[str, Header(alias="X-Tenant-ID")]
RequestID = Annotated[str, Header(alias="X-Request-ID")]
CorrelationID = Annotated[str, Header(alias="X-Correlation-ID")]


@lru_cache
def controller() -> RestrictedController:
    secret_path = Path(settings.controller_approval_signing_key_file)
    secret = secret_path.read_bytes() if secret_path.is_file() else b""
    roots = tuple(
        Path(item.strip()) for item in settings.controller_workspace_allowlist.split(",")
        if item.strip()
    )
    return RestrictedController(ApprovalTokens(secret), roots)


def _controller() -> RestrictedController:
    try:
        return controller()
    except (OSError, ControllerError) as exc:
        raise HTTPException(503, "controller signing authority unavailable") from exc


def _repository(session: AsyncSession) -> RestrictedController | PostgresControllerRepository:
    backend = settings.controller_repository_backend.strip().lower()
    if backend == "memory":
        if settings.controller_private_enabled:
            raise HTTPException(503, "in-memory controller backend denied in private mode")
        return _controller()
    if backend != "postgres" or not settings.database_url.strip():
        raise HTTPException(503, "controller PostgreSQL backend unavailable")
    return PostgresControllerRepository(session, _controller().tokens)


async def _call(repository: Any, operation: str, *args: Any, **kwargs: Any) -> Any:
    try:
        result = getattr(repository, operation)(*args, **kwargs)
        return await result if isawaitable(result) else result
    except SQLAlchemyError as exc:
        raise HTTPException(503, "controller PostgreSQL backend unavailable") from exc


def _public(repository: Any, value: Any) -> dict[str, Any]:
    return value.public() if hasattr(value, "public") else repository.public(value)


def _task_id(repository: Any, value: str) -> str | UUID:
    return UUID(value) if isinstance(repository, PostgresControllerRepository) else value


def _error(exc: ControllerError) -> HTTPException:
    message = str(exc)
    if "not found" in message:
        return HTTPException(404, message)
    if "expired" in message or "invalid" in message or "replay" in message or "scope" in message:
        return HTTPException(401, message)
    if "conflict" in message or "state transition" in message or "approval does not" in message:
        return HTTPException(409, message)
    return HTTPException(403, message)


@router.post("/tasks", status_code=201)
async def create_task(body: TaskCreate, tenant_id: Tenant, request_id: RequestID,
                      correlation_id: CorrelationID,
                      idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
                      session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        task, replay = await _call(repository, "create_task",
            body.model_dump(), tenant_id=_required(tenant_id, "tenant_id"),
            request_id=_required(request_id, "request_id"),
            correlation_id=_required(correlation_id, "correlation_id"),
            idempotency_key=_required(idempotency_key, "idempotency_key"),
        )
        return {**_public(repository, task), "idempotent_replay": replay}
    except ControllerError as exc:
        raise _error(exc) from exc


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, tenant_id: Tenant, session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        return _public(repository, await _call(repository, "get_task", _task_id(repository, task_id), tenant_id))
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/tasks/{task_id}/plan")
async def plan_task(task_id: str, body: PlanCreate, tenant_id: Tenant,
                    session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        value = await _call(repository, "plan", _task_id(repository, task_id), tenant_id,
                            [step.model_dump() for step in body.steps])
        return _public(repository, value)
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/tasks/{task_id}/approve")
async def approve_task(task_id: str, body: Approval, tenant_id: Tenant,
                       actor_id: Annotated[str, Header(alias="X-Actor-ID")],
                       session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        task, token = await _call(repository, "approve", _task_id(repository, task_id), tenant_id,
            body.plan_hash, _required(actor_id, "actor_id"), body.server_id)
        return {**_public(repository, task), "approval_token": token,
                "expires_in": _controller().tokens.ttl_seconds}
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, tenant_id: Tenant, session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        return _public(repository, await _call(repository, "cancel", _task_id(repository, task_id), tenant_id))
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/tasks/{task_id}/reject")
async def reject_task(task_id: str, tenant_id: Tenant,
                      actor_id: Annotated[str, Header(alias="X-Actor-ID")],
                      session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        return _public(repository, await _call(repository, "reject", _task_id(repository, task_id), tenant_id,
                       _required(actor_id, "actor_id")))
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/tasks/{task_id}/queue")
async def queue_task(task_id: str, body: QueueTask, tenant_id: Tenant,
                     session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        return _public(repository, await _call(repository, "queue", _task_id(repository, task_id), tenant_id,
                       **body.model_dump()))
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/tasks/{task_id}/suspend")
async def suspend_task(task_id: str, tenant_id: Tenant, session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        return _public(repository, await _call(repository, "suspend", _task_id(repository, task_id), tenant_id))
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str, tenant_id: Tenant, session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        return _public(repository, await _call(repository, "resume", _task_id(repository, task_id), tenant_id))
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/scheduler/claim")
async def claim_task(body: WorkerClaim, session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        task = await _call(repository, "claim", **body.model_dump())
        return {"task": _public(repository, task) if task else None}
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/scheduler/tasks/{task_id}/heartbeat")
async def heartbeat_task(task_id: str, body: WorkerLease, session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        data = body.model_dump()
        worker = f"{data.pop('server_id')}:{data.pop('worker_id')}"
        value: Any
        if isinstance(repository, PostgresControllerRepository):
            value = await repository.heartbeat(UUID(task_id), data.pop("tenant_id"), worker,
                data.pop("expected_version"), data.pop("lease_seconds"))
        else:
            value = repository.heartbeat(task_id, data.pop("tenant_id"), worker.split(":", 1)[1],
                                         data.pop("lease_seconds"))
        return _public(repository, value)
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/scheduler/tasks/{task_id}/finish")
async def finish_task(task_id: str, body: WorkerFinish, session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        data = body.model_dump()
        worker = f"{data.pop('server_id')}:{data.pop('worker_id')}"
        value: Any
        if isinstance(repository, PostgresControllerRepository):
            value = await repository.finish(UUID(task_id), data.pop("tenant_id"), worker,
                data.pop("expected_version"), data.pop("evidence"))
        else:
            value = repository.finish(task_id, data.pop("tenant_id"), worker.split(":", 1)[1],
                                      data.pop("evidence"))
        return _public(repository, value)
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/scheduler/tasks/{task_id}/fail")
async def fail_task(task_id: str, body: WorkerFail, session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        data = body.model_dump()
        worker = f"{data.pop('server_id')}:{data.pop('worker_id')}"
        value: Any
        if isinstance(repository, PostgresControllerRepository):
            value = await repository.fail(UUID(task_id), data.pop("tenant_id"), worker,
                data.pop("expected_version"), data.pop("error_code"), data.pop("retryable"))
        else:
            value = repository.fail(task_id, data.pop("tenant_id"), worker.split(":", 1)[1],
                data.pop("error_code"), retryable=data.pop("retryable"))
        return _public(repository, value)
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/scheduler/recover")
async def recover_tasks(session: AsyncSession = Depends(get_session)):
    return await _call(_repository(session), "recover_expired")


@router.post("/executions", status_code=202)
@router.post("/tools/execute", status_code=202)
async def create_execution(body: ExecutionCreate, tenant_id: Tenant,
                           request_id: RequestID, correlation_id: CorrelationID,
                           session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        execution = await _call(repository, "execute",
            **body.model_dump(exclude={"approval_token", "task_id"}),
            task_id=_task_id(repository, body.task_id), tenant_id=tenant_id,
            token=body.approval_token, request_id=request_id,
            correlation_id=correlation_id,
        )
        verification = await _call(repository, "verification",
                                   _task_id(repository, execution["execution_id"]), tenant_id)
        return {**execution, "verification_code": verification["verification_code"]}
    except ControllerError as exc:
        raise _error(exc) from exc


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str, tenant_id: Tenant,
                        session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        if isinstance(repository, PostgresControllerRepository):
            return await repository.get_execution(UUID(execution_id), tenant_id)
        record = repository.executions.get(execution_id)
        if record is None or record["tenant_id"] != tenant_id:
            raise ControllerError("execution not found")
        return record
    except ControllerError as exc:
        raise _error(exc) from exc


@router.get("/verifications/{verification_code}")
async def get_verification(verification_code: str, tenant_id: Tenant,
                           session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        if isinstance(repository, PostgresControllerRepository):
            return await repository.get_verification(verification_code, tenant_id)
        record = repository.verifications.get(verification_code)
        if record is None or record["tenant_id"] != tenant_id:
            raise ControllerError("verification not found")
        return record
    except ControllerError as exc:
        raise _error(exc) from exc


@router.get("/audit/{task_id}")
async def get_audit(task_id: str, tenant_id: Tenant, session: AsyncSession = Depends(get_session)):
    try:
        repository = _repository(session)
        if isinstance(repository, PostgresControllerRepository):
            records = await repository.get_audit(UUID(task_id), tenant_id)
        else:
            repository.get_task(task_id, tenant_id)
            records = repository.audits.get(task_id, [])
        return {"task_id": task_id, "records": records}
    except ControllerError as exc:
        raise _error(exc) from exc


@router.post("/agents/register", status_code=201)
async def register_agent(body: AgentRegistration):
    try:
        return _controller().register_agent(body.model_dump())
    except ControllerError as exc:
        raise _error(exc) from exc


@router.get("/agents")
async def list_agents():
    return {"agents": list(_controller().agents.values())}
