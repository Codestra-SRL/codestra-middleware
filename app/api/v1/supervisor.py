from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.supervisor.security import SupervisorPrincipal, require_supervisor
from app.supervisor.service import STORE

router = APIRouter(prefix="/api/v1/supervisor", tags=["supervisor"])
Principal = Annotated[SupervisorPrincipal, Depends(require_supervisor)]


class Mutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=256)
    note: str | None = Field(default=None, max_length=2000)
    scheduled_at: str | None = None
    assignee_id: str | None = Field(default=None, pattern=r"^[A-Z0-9-]{1,64}$")


def _enabled() -> None:
    if (
        not settings.supervisor_console_staging_enabled
        or settings.environment == "production"
    ):
        raise HTTPException(404, "supervisor console unavailable")


def _list(
    rows: list[dict[str, Any]],
    principal: SupervisorPrincipal,
    team_id: str | None = None,
) -> dict[str, Any]:
    scoped = STORE.scoped(rows, principal)
    if team_id:
        principal.authorize_team(team_id)
        scoped = [row for row in scoped if row.get("team_id") == team_id]
    return {"items": scoped, "count": len(scoped), "synthetic": True}


@router.get("/overview")
async def overview(principal: Principal) -> dict[str, Any]:
    _enabled()
    agents, calls, callbacks = (
        STORE.scoped(rows, principal)
        for rows in (STORE.agents, STORE.calls, STORE.callbacks)
    )
    counts = {
        state.lower(): sum(a["state"] == state for a in agents)
        for state in ("READY", "ON_CALL", "PAUSED", "WRAP_UP", "UNAVAILABLE")
    }
    return {
        "agents_logged_in": len(agents),
        **{f"agents_{k}": v for k, v in counts.items()},
        "active_calls": sum(c["state"] == "ACTIVE" for c in calls),
        "calls_waiting": sum(c["state"] == "WAITING" for c in calls),
        "callbacks_due": sum(c["status"] == "SCHEDULED" for c in callbacks),
        "callbacks_overdue": sum(c["status"] == "OVERDUE" for c in callbacks),
        "qa_reviews_pending": len(STORE.scoped(STORE.qa, principal)),
        "compliance_alerts_open": len(STORE.scoped(STORE.compliance, principal)),
        "targets": {
            "asa_seconds": 20,
            "abandon_rate": 0.03,
            "occupancy": [0.85, 0.92],
            "adherence": 0.90,
            "transfer_success": 0.80,
            "callback_sla_seconds": 7200,
            "fcr": 0.70,
            "qa": 0.85,
        },
        "synthetic": True,
    }


@router.get("/agents")
async def agents(principal: Principal, team_id: str | None = None):
    _enabled()
    return _list(STORE.agents, principal, team_id)


@router.get("/agents/{agent_id}")
async def agent(agent_id: str, principal: Principal):
    _enabled()
    return STORE.get(STORE.agents, agent_id, principal)


@router.get("/agents/{agent_id}/timeline")
async def timeline(agent_id: str, principal: Principal):
    _enabled()
    item = STORE.get(STORE.agents, agent_id, principal)
    return {"agent_id": item["id"], "items": [], "synthetic": True}


@router.post("/agents/{agent_id}/coaching-note", status_code=202)
async def coaching_note(
    agent_id: str,
    payload: Mutation,
    principal: Principal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    _enabled()
    principal.require(
        "CALL_CENTER_SUPERVISOR", "CALL_CENTER_MANAGER", "QA_REVIEWER", "QA_MANAGER"
    )
    agent = STORE.get(STORE.agents, agent_id, principal)
    record = {
        "id": f"COACH-{len(STORE.coaching) + 1:03}",
        "tenant_id": principal.tenant_id,
        "workspace_id": principal.workspace_id,
        "team_id": agent["team_id"],
        "status": "DRAFT",
        "topic": payload.note or "Supervisor coaching",
    }
    STORE.coaching.append(record)
    return STORE.mutate(
        action="coaching.create",
        resource=record,
        principal=principal,
        idempotency_key=idempotency_key,
        reason=payload.reason,
        changes={},
    )


@router.post("/agents/{agent_id}/status-refresh", status_code=403)
async def status_refresh(agent_id: str, payload: Mutation, principal: Principal):
    _enabled()
    STORE.get(STORE.agents, agent_id, principal)
    raise HTTPException(403, "supervisor agent commands are disabled")


@router.get("/calls")
async def calls(principal: Principal, team_id: str | None = None):
    _enabled()
    return _list(STORE.calls, principal, team_id)


@router.get("/calls/{call_id}")
async def call(call_id: str, principal: Principal):
    _enabled()
    return STORE.get(STORE.calls, call_id, principal)


@router.get("/campaigns")
async def campaigns(principal: Principal):
    _enabled()
    return _list(STORE.campaigns, principal)


@router.get("/campaigns/{campaign_id}")
async def campaign(campaign_id: str, principal: Principal):
    _enabled()
    return STORE.get(STORE.campaigns, campaign_id, principal)


@router.get("/callbacks")
async def callbacks(principal: Principal):
    _enabled()
    return _list(STORE.callbacks, principal)


@router.post("/callbacks/{callback_id}/{action}", status_code=202)
async def callback_action(
    callback_id: str,
    action: str,
    payload: Mutation,
    principal: Principal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    _enabled()
    principal.require("CALL_CENTER_SUPERVISOR", "CALL_CENTER_MANAGER")
    if action not in {"assign", "reschedule", "cancel"}:
        raise HTTPException(404, "operation not found")
    callback = STORE.get(STORE.callbacks, callback_id, principal)
    return STORE.mutate(
        action=f"callback.{action}",
        resource=callback,
        principal=principal,
        idempotency_key=idempotency_key,
        reason=payload.reason,
        changes={"status": action.upper()},
    )


@router.get("/qa")
async def qa(principal: Principal):
    _enabled()
    principal.require("QA_REVIEWER", "QA_MANAGER", "CALL_CENTER_MANAGER")
    return _list(STORE.qa, principal)


@router.post("/qa/{qa_id}/review", status_code=202)
async def qa_review(
    qa_id: str,
    payload: Mutation,
    principal: Principal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    _enabled()
    principal.require("QA_REVIEWER", "QA_MANAGER")
    record = STORE.get(STORE.qa, qa_id, principal)
    return STORE.mutate(
        action="qa.human_review",
        resource=record,
        principal=principal,
        idempotency_key=idempotency_key,
        reason=payload.reason,
        changes={"status": "HUMAN_REVIEWED"},
    )


@router.get("/compliance")
async def compliance(principal: Principal):
    _enabled()
    principal.require("COMPLIANCE_REVIEWER", "CALL_CENTER_MANAGER")
    return _list(STORE.compliance, principal)


@router.post("/compliance/{alert_id}/{action}", status_code=202)
async def compliance_action(
    alert_id: str,
    action: str,
    payload: Mutation,
    principal: Principal,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
):
    _enabled()
    principal.require("COMPLIANCE_REVIEWER")
    if action not in {"assign", "resolve"}:
        raise HTTPException(404, "operation not found")
    record = STORE.get(STORE.compliance, alert_id, principal)
    return STORE.mutate(
        action=f"compliance.{action}",
        resource=record,
        principal=principal,
        idempotency_key=idempotency_key,
        reason=payload.reason,
        changes={"status": "HUMAN_RESOLVED" if action == "resolve" else "ASSIGNED"},
    )


@router.get("/workforce")
@router.get("/adherence")
@router.get("/schedules")
async def workforce(principal: Principal):
    _enabled()
    principal.require("WORKFORCE_MANAGER", "CALL_CENTER_MANAGER")
    agents = STORE.scoped(STORE.agents, principal)
    return {
        "items": [
            {
                "agent_id": a["id"],
                "team_id": a["team_id"],
                "occupancy": a["occupancy"],
                "adherence": a["adherence"],
                "status": "ON_SCHEDULE",
            }
            for a in agents
        ],
        "synthetic": True,
    }


@router.get("/events")
async def events(
    request: Request, principal: Principal, last_event_id: int = Query(default=0, ge=0)
):
    _enabled()

    async def stream():
        sequence = last_event_id
        for _ in range(3):
            if await request.is_disconnected():
                return
            sequence += 1
            payload = {
                "sequence": sequence,
                "type": "heartbeat",
                "tenant_id": principal.tenant_id,
                "workspace_id": principal.workspace_id,
            }
            encoded = json.dumps(payload, separators=(",", ":"))
            if len(encoded) > settings.supervisor_max_event_bytes:
                raise RuntimeError("event too large")
            yield f"id: {sequence}\nevent: heartbeat\ndata: {encoded}\n\n"
            await asyncio.sleep(0.01)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/campaigns/{campaign_id}/activate", status_code=403)
async def campaign_activate(campaign_id: str, payload: Mutation, principal: Principal):
    _enabled()
    STORE.get(STORE.campaigns, campaign_id, principal)
    raise HTTPException(403, "campaign commands are disabled")
