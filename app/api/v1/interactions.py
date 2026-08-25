"""Authoritative persistence for agent post-call actions.

Replaces the agent desktop's mocked disposition/notes/callback save path
(AGENT-01). Every write here is: transactional, idempotent (via the shared
IdempotencyRecord table), attributed to a validated authenticated agent, and
audited. A failed write always returns a real error status -- this router
must never report success for data that was not durably persisted.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.control import Idem, persist
from app.core.agent_identity import authenticate_agent
from app.db.models import IdempotencyRecord, InteractionResult, OutboxEvent
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/interactions", tags=["interactions"])

INTERACTION_ID_PATTERN = r"^[A-Za-z0-9_.-]{1,144}$"
LEAD_ID_PATTERN = r"^[A-Za-z0-9_.-]{1,144}$"


class NotesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    crm_lead_public_id: str = Field(min_length=1, max_length=144, pattern=LEAD_ID_PATTERN)
    notes_text: str = Field(min_length=1, max_length=8000)


class DispositionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    crm_lead_public_id: str = Field(min_length=1, max_length=144, pattern=LEAD_ID_PATTERN)
    disposition_code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9_-]+$")


class CallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    crm_lead_public_id: str = Field(min_length=1, max_length=144, pattern=LEAD_ID_PATTERN)
    scheduled_for: datetime
    timezone: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=2000)


InteractionBody = NotesRequest | DispositionRequest | CallbackRequest


async def _write(
    db: AsyncSession,
    request: Request,
    interaction_id: str,
    result_type: str,
    body: InteractionBody,
    fields: dict,
    idempotency_key: str | None,
    x_correlation_id: str | None,
) -> dict:
    agent = await authenticate_agent(request)
    row_body = {"interaction_id": interaction_id, "result_type": result_type, **body.model_dump(mode="json")}
    scope = f"interactions/{result_type}"
    row, request_hash, key_hash = await Idem.check(db, idempotency_key, scope, row_body)
    if row:
        return row.response
    correlation_id = x_correlation_id or str(uuid4())
    result = InteractionResult(
        interaction_public_id=interaction_id,
        result_type=result_type,
        agent_subject=agent.subject,
        agent_employee_id=agent.employee_id,
        crm_lead_public_id=body.crm_lead_public_id,
        correlation_id=correlation_id,
        idempotency_key_hash=key_hash,
        **fields,
    )
    db.add(result)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "duplicate interaction result") from exc
    db.add(
        OutboxEvent(
            topic="interaction.result.recorded",
            payload={
                "interaction_result_id": str(result.id),
                "interaction_public_id": interaction_id,
                "result_type": result_type,
                "agent_employee_id": agent.employee_id,
                "agent_odoo_employee_id": agent.odoo_employee_id,
                "crm_lead_public_id": body.crm_lead_public_id,
                **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in fields.items()},
                "correlation_id": correlation_id,
            },
            correlation_id=correlation_id,
        )
    )
    await persist(
        db,
        f"interaction.{result_type}.recorded",
        str(result.id),
        correlation_id,
        row_body,
    )
    response = {
        "interaction_result_id": str(result.id),
        "status": "accepted",
        "correlation_id": correlation_id,
    }
    db.add(
        IdempotencyRecord(
            scope=scope,
            key_hash=key_hash,
            request_hash=request_hash,
            response=response,
            status_code=202,
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "duplicate interaction result") from exc
    except Exception as exc:  # pragma: no cover - defensive: never lie about success
        await db.rollback()
        raise HTTPException(500, "interaction result could not be persisted") from exc
    return response


@router.post("/{interaction_id}/notes", status_code=202)
async def save_notes(
    body: NotesRequest,
    request: Request,
    interaction_id: str = Path(pattern=INTERACTION_ID_PATTERN),
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
):
    return await _write(
        db, request, interaction_id, "notes", body,
        {"notes_text": body.notes_text}, idempotency_key, x_correlation_id,
    )


@router.post("/{interaction_id}/disposition", status_code=202)
async def save_disposition(
    body: DispositionRequest,
    request: Request,
    interaction_id: str = Path(pattern=INTERACTION_ID_PATTERN),
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
):
    return await _write(
        db, request, interaction_id, "disposition", body,
        {"disposition_code": body.disposition_code}, idempotency_key, x_correlation_id,
    )


@router.post("/{interaction_id}/callback", status_code=202)
async def schedule_callback(
    body: CallbackRequest,
    request: Request,
    interaction_id: str = Path(pattern=INTERACTION_ID_PATTERN),
    db: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_correlation_id: str | None = Header(None, alias="X-Correlation-ID"),
):
    if body.scheduled_for <= datetime.now(body.scheduled_for.tzinfo):
        raise HTTPException(422, "callback must be scheduled in the future")
    return await _write(
        db, request, interaction_id, "callback", body,
        {
            "callback_scheduled_for": body.scheduled_for,
            "callback_timezone": body.timezone,
            "callback_reason": body.reason,
        },
        idempotency_key, x_correlation_id,
    )


@router.get("/{interaction_id}/results")
async def list_results(
    interaction_id: str = Path(pattern=INTERACTION_ID_PATTERN),
    db: AsyncSession = Depends(get_session),
):
    rows = (
        await db.execute(
            select(InteractionResult).where(
                InteractionResult.interaction_public_id == interaction_id
            )
        )
    ).scalars().all()
    return {
        "interaction_id": interaction_id,
        "results": [
            {
                "id": str(r.id),
                "result_type": r.result_type,
                "delivery_status": r.delivery_status,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }
