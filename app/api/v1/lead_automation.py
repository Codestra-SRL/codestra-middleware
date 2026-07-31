from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.core.lead_automation import (
    Conflict,
    LeadAutomationError,
    LeadAutomationService,
)
from app.core.lead_callback_auth import CallbackAuthenticationError, verify_callback

router = APIRouter(tags=["lead-automation"])
service = LeadAutomationService()
service.enabled = settings.lead_automation_enabled
service.binding_enabled = settings.n8n_lead_binding_enabled
service.result_processing_enabled = settings.n8n_result_processing_enabled
service.odoo_apply_enabled = settings.odoo_lead_apply_enabled
service.action_switches.update(
    {
        "CREATE_LEAD": settings.lead_create_enabled,
        "UPDATE_ALLOWLISTED_FIELDS": settings.lead_update_enabled,
        "ASSIGN_AUTHORIZED_TEAM": settings.lead_assignment_enabled,
        "ASSIGN_AUTHORIZED_USER": settings.lead_assignment_enabled,
        "CHANGE_AUTHORIZED_STAGE": settings.lead_status_change_enabled,
        "CREATE_INTERNAL_CALLBACK_ACTIVITY": settings.lead_callback_create_enabled,
    }
)
used_callback_nonces: set[tuple[str, str]] = set()


@router.post("/api/v1/events/odoo", status_code=202)
def receive_odoo_event(
    body: dict, idempotency_key: str = Header("", alias="Idempotency-Key")
):
    if body.get("idempotency_key") != idempotency_key:
        raise HTTPException(409, "idempotency binding mismatch")
    try:
        return service.receive(body)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except LeadAutomationError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/api/v1/lead-automation/results")
async def receive_result(request: Request):
    raw = await request.body()
    body = await request.json()
    try:
        verify_callback(
            body=raw,
            headers={
                name: request.headers.get(name, "")
                for name in (
                    "X-Service-Identity",
                    "X-Service-Audience",
                    "X-Codestra-Timestamp",
                    "X-Codestra-Nonce",
                    "X-Codestra-Content-SHA256",
                    "X-Codestra-Signature",
                    "Idempotency-Key",
                    "X-Codestra-Environment",
                )
            },
            secret=settings.lead_automation_hmac_secret.encode(),
            environment=body.get("environment", ""),
            used_nonces=used_callback_nonces,
        )
    except CallbackAuthenticationError as exc:
        raise HTTPException(401, str(exc)) from exc
    try:
        return service.receive_result(body)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except LeadAutomationError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/api/v1/lead-automation/events/{automation_event_id}")
def status(automation_event_id: str):
    try:
        return service.status(service._find(automation_event_id))
    except LeadAutomationError as exc:
        raise HTTPException(404, str(exc)) from exc
