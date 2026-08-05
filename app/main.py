import re
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.api.v1.automation import router as automation_router
from app.api.v1.ai import lead_intelligence_router, router as ai_router, workflow_router
from app.api.v1.campaign_search import router as campaign_search_router
from app.api.v1.commands import router as commands_router
from app.api.v1.control import router as control_router
from app.api.v1.events import router as events_router
from app.api.v1.lead_automation import router as lead_automation_router
from app.api.v1.lead_reconciliation import router as lead_reconciliation_router
from app.api.v1.mappings import router as mappings_router
from app.api.v1.n8n_staging import router as n8n_staging_router
from app.api.v1.n8n_target import router as n8n_target_router
from app.api.v1.n8n_transport import router as n8n_transport_router
from app.api.v1.operations import router as operations_router
from app.api.v1.orchestration import router as orchestration_router
from app.api.v1.publisher import router as publisher_router
from app.api.v1.recordings import router as recordings_router
from app.api.v1.customer_portal import router as customer_portal_router
from app.api.v1.bi import router as bi_router
from app.api.v1.saas import router as saas_router
from app.api.v1.marketplace import router as marketplace_router
from app.api.v1.developer import router as developer_router
from app.api.v1.mobile import router as mobile_router
from app.api.v1.voice import router as voice_router
from app.api.v1.ai_governance import router as ai_governance_router
from app.api.v1.healthcare import router as healthcare_router
from app.api.v1.finance import router as finance_router
from app.api.v1.legal import router as legal_router
from app.api.v1.support import router as support_router
from app.api.v1.revops import router as revops_router
from app.api.v1.enterprise import router as enterprise_router
from app.api.v1.registry import router as registry_router
from app.api.v1.reports import router as reports_router
from app.api.v1.social import router as social_router
from app.api.v1.telephony import router as telephony_router
from app.api.v1.vicidial_assignments import router as vicidial_assignments_router
from app.api.v1.vicidial_canary import router as vicidial_canary_router
from app.api.v1.call_intelligence import router as call_intelligence_router
from app.api.v1.ai_control_center import router as ai_control_center_router
from app.api.v1.webphone import router as webphone_router
from app.core.auth import BearerAuthError, verify_bearer
from app.core.config import settings

app = FastAPI(title="Codestra Middleware", version="0.2.0")
app.include_router(events_router)
app.include_router(control_router)
app.include_router(automation_router)
app.include_router(ai_router)
app.include_router(lead_intelligence_router)
app.include_router(workflow_router)
app.include_router(reports_router)
app.include_router(operations_router)
app.include_router(lead_reconciliation_router)
app.include_router(lead_automation_router)
app.include_router(orchestration_router)
app.include_router(mappings_router)
app.include_router(publisher_router)
app.include_router(webphone_router)
app.include_router(n8n_staging_router)
app.include_router(n8n_transport_router)
app.include_router(n8n_target_router)
app.include_router(telephony_router)
app.include_router(vicidial_assignments_router)
app.include_router(vicidial_canary_router)
app.include_router(call_intelligence_router)
app.include_router(ai_control_center_router)
app.include_router(social_router)
app.include_router(campaign_search_router)
app.include_router(registry_router)
app.include_router(commands_router)
app.include_router(recordings_router)
app.include_router(customer_portal_router)
app.include_router(bi_router)
app.include_router(saas_router)
app.include_router(marketplace_router)
app.include_router(developer_router)
app.include_router(mobile_router)
app.include_router(voice_router)
app.include_router(ai_governance_router)
app.include_router(healthcare_router)
app.include_router(finance_router)
app.include_router(legal_router)
app.include_router(support_router)
app.include_router(revops_router)
app.include_router(enterprise_router)
app.mount("/metrics", make_asgi_app())


@app.exception_handler(RequestValidationError)
async def privacy_safe_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return useful locations/codes without reflecting submitted content."""
    errors = [
        {"type": item["type"], "loc": item["loc"], "msg": item["msg"]}
        for item in exc.errors()
    ]
    return JSONResponse({"detail": errors}, status_code=422)


SIGNED_WEBHOOK_PATHS = frozenset(
    {
        "/api/v1/events/vicidial",
        "/api/v1/automation/events",
        "/api/v2/telephony/canary",
        "/api/v1/n8n/executions",
        "/api/v1/n8n/executions/register",
        "/api/v1/n8n/acknowledgements",
        "/api/v1/lead-automation/results",
        "/api/v1/registry/resolve",
        "/api/v1/social/provider-events",
        "/api/v1/workflow-results",
    }
)
SELF_AUTHENTICATED_PATHS = frozenset({"/v1/registry/search"})
N8N_TRANSITION_PATH = re.compile(
    r"^/api/v1/n8n/executions/[0-9a-fA-F-]{36}/transitions$"
)
AI_RESULT_PATH = re.compile(r"^/api/v1/ai/jobs/[0-9a-fA-F-]{36}/result$")
RECORDING_EXPORTER_PATH = re.compile(
    r"^/api/v1/recordings(?:/reservations|/REC-[0-9a-f]{32}/(?:complete|failure))$"
)


@app.middleware("http")
async def control_request_guard(request: Request, call_next):
    supplied_correlation = request.headers.get("X-Correlation-ID", "")
    correlation_id = (
        supplied_correlation
        if supplied_correlation and len(supplied_correlation) <= 128
        else str(uuid4())
    )
    if (
        int(request.headers.get("content-length", "0") or 0)
        > settings.request_max_bytes
    ):
        response = JSONResponse({"detail": "request too large"}, status_code=413)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    if (
        (request.url.path.startswith("/api/") or request.url.path.startswith("/v1/"))
        and request.url.path not in SIGNED_WEBHOOK_PATHS
        and not RECORDING_EXPORTER_PATH.fullmatch(request.url.path)
        and not (
            request.method == "POST" and N8N_TRANSITION_PATH.fullmatch(request.url.path)
        )
        and not (request.method == "POST" and AI_RESULT_PATH.fullmatch(request.url.path))
        and request.url.path not in SELF_AUTHENTICATED_PATHS
    ):
        try:
            verify_bearer(
                request.headers.get("Authorization", ""), settings.middleware_secret
            )
        except BearerAuthError as exc:
            status_code = 503 if not settings.middleware_secret else 401
            response = JSONResponse({"detail": str(exc)}, status_code=status_code)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.get("/healthz")
@app.get("/health")
@app.get("/health/live")
async def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": "dry-run",
        "authorization": "online" if settings.auth_ready else "offline",
    }


@app.get("/readyz", response_model=None)
@app.get("/readiness", response_model=None)
@app.get("/health/ready", response_model=None)
async def readyz() -> dict[str, str] | JSONResponse:
    if not settings.auth_ready:
        return JSONResponse(
            {"status": "not-ready", "authorization": "offline"}, status_code=503
        )
    return {"status": "ready", "integration": "outbox-only", "authorization": "online"}


@app.get("/.well-known/codestra-service")
async def service_identity() -> dict[str, object]:
    return {
        "service": "codestra-recording-api",
        "contract_version": "1.0",
        "hostname": "api.staging.internal.codestra.agency",
        "tls_sni_required": True,
    }


@app.get("/version")
async def version() -> dict[str, str]:
    return {
        "service": "codestra-contact-center-middleware",
        "version": "1.0.0",
        "environment": settings.environment,
    }
