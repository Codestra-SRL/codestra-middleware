from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.automation import (
    AutomationSecurityError,
    redact,
    verify_exact_body,
    verify_timestamp,
)
from app.core.config import settings

router = APIRouter(prefix="/api/v1/automation", tags=["automation"])


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]+$")
    event_version: str = Field(pattern=r"^1(?:\.\d+)?$")
    environment: Literal["test", "staging", "integration", "production"]
    source: str = Field(min_length=1, max_length=64)
    campaign_id: str = Field(min_length=1, max_length=64)
    correlation_id: str = Field(min_length=1, max_length=128)
    occurred_at: datetime
    payload: dict[str, Any]


def enforce_scope(envelope: EventEnvelope) -> None:
    if envelope.environment != settings.automation_environment:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "environment not permitted")
    if envelope.campaign_id not in settings.allowed_campaigns:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "campaign not permitted")


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def receive_event(
    request: Request,
    x_codestra_event_id: str = Header(alias="X-Codestra-Event-ID"),
    x_codestra_workflow_id: str = Header(alias="X-Codestra-Workflow-ID"),
    x_codestra_timestamp: str = Header(alias="X-Codestra-Timestamp"),
    x_codestra_signature: str = Header(alias="X-Codestra-Signature"),
) -> dict[str, Any]:
    body = await request.body()
    try:
        verify_timestamp(
            x_codestra_timestamp, ttl_seconds=settings.signature_ttl_seconds
        )
        verify_exact_body(body, x_codestra_signature, settings.webhook_shared_secret)
        envelope = EventEnvelope.model_validate_json(body)
    except AutomationSecurityError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "invalid event schema"
        ) from exc
    if envelope.event_id != x_codestra_event_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "event identifier mismatch"
        )
    if not x_codestra_workflow_id.startswith("WF-"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "workflow not permitted")
    enforce_scope(envelope)
    if not settings.n8n_event_delivery_enabled:
        return {
            "accepted": True,
            "event_id": envelope.event_id,
            "status": "delivery_disabled",
        }
    return {"accepted": True, "event_id": envelope.event_id, "status": "queued"}


@router.post("/policy-check")
async def policy_check(body: EventEnvelope) -> dict[str, Any]:
    enforce_scope(body)
    return {
        "allowed": True,
        "environment": body.environment,
        "campaign_id": body.campaign_id,
        "workflow_id": "validated-by-router",
    }


class Lifecycle(BaseModel):
    event_id: str
    workflow_id: str
    execution_reference: str
    attempt_number: int = Field(ge=1)
    details: dict[str, Any] = Field(default_factory=dict)


@router.post("/executions/{transition}", status_code=202)
async def execution_transition(
    transition: Literal["start", "complete", "fail", "retry"], body: Lifecycle
) -> dict[str, Any]:
    return {
        "accepted": True,
        "transition": transition,
        "event_id": body.event_id,
        "details": redact(body.details),
    }


@router.post("/events/dead-letter", status_code=202)
async def dead_letter(body: Lifecycle) -> dict[str, Any]:
    return {
        "accepted": True,
        "status": "dead_lettered",
        "event_id": body.event_id,
        "details": redact(body.details),
    }


@router.get("/events/{event_id}")
async def event_status(event_id: str) -> dict[str, str]:
    return {"event_id": event_id, "status": "not_persisted_in_safe_blueprint"}


CONTEXT_RESOURCES = {"calls", "leads", "agents", "campaigns", "timeline"}


@router.get("/context/{resource}/{identifier}")
async def context(resource: str, identifier: str) -> dict[str, Any]:
    if resource not in CONTEXT_RESOURCES:
        raise HTTPException(404, "unknown context resource")
    if not settings.vicidial_read_enabled:
        raise HTTPException(503, "VICIDIAL_READ_ENABLED is false")
    return {"resource": resource, "identifier": identifier, "data": {}}


@router.get("/callbacks/{state}")
async def callbacks(state: Literal["due", "overdue"]) -> dict[str, Any]:
    return {"state": state, "timezone": "America/Santo_Domingo", "items": []}


@router.get("/queues/status")
async def queue_status() -> dict[str, Any]:
    return {"campaigns": [], "generated_at": datetime.now(timezone.utc)}


ACTION_NAMES = {
    "lead-enrichment",
    "callbacks",
    "notifications",
    "lead-priority",
    "lead-assignment",
    "qa-review",
    "contact-suppression",
    "report-delivery",
}


@router.post("/actions/{action}", status_code=202)
async def authorized_action(action: str, body: dict[str, Any]) -> dict[str, Any]:
    if action not in ACTION_NAMES:
        raise HTTPException(404, "unknown action")
    if not settings.automation_actions_enabled:
        raise HTTPException(503, "AUTOMATION_ACTIONS_ENABLED is false")
    campaign = body.get("campaign_id")
    if campaign not in settings.allowed_campaigns:
        raise HTTPException(403, "campaign not permitted")
    return {"accepted": True, "action": action, "payload": redact(body)}
