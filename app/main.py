import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.api.v1.automation import router as automation_router
from app.api.v1.allocations import router as allocations_router
from app.api.v1.campaign_search import router as campaign_search_router
from app.api.v1.control import router as control_router
from app.api.v1.events import router as events_router
from app.api.v1.lead_reconciliation import router as lead_reconciliation_router
from app.api.v1.mappings import router as mappings_router
from app.api.v1.n8n_staging import router as n8n_staging_router
from app.api.v1.n8n_target import router as n8n_target_router
from app.api.v1.n8n_transport import router as n8n_transport_router
from app.api.v1.operations import router as operations_router
from app.api.v1.orchestration import router as orchestration_router
from app.api.v1.publisher import router as publisher_router
from app.api.v1.reports import router as reports_router
from app.api.v1.registry import router as registry_router
from app.api.v1.schemas import internal_router as internal_schemas_router
from app.api.v1.schemas import router as schemas_router
from app.api.v1.telephony import router as telephony_router
from app.api.v1.webphone import router as webphone_router
from app.core.auth import BearerAuthError, verify_bearer
from app.core.config import settings

app = FastAPI(title="Codestra Middleware", version="0.2.0")
app.include_router(events_router)
app.include_router(control_router)
app.include_router(automation_router)
app.include_router(allocations_router)
app.include_router(reports_router)
app.include_router(operations_router)
app.include_router(lead_reconciliation_router)
app.include_router(orchestration_router)
app.include_router(mappings_router)
app.include_router(publisher_router)
app.include_router(webphone_router)
app.include_router(n8n_staging_router)
app.include_router(n8n_transport_router)
app.include_router(n8n_target_router)
app.include_router(telephony_router)
app.include_router(campaign_search_router)
app.include_router(registry_router)
app.include_router(schemas_router)
app.include_router(internal_schemas_router)
app.mount("/metrics", make_asgi_app())

SIGNED_WEBHOOK_PATHS = frozenset(
    {
        "/api/v1/events/vicidial",
        "/api/v1/automation/events",
        "/api/v2/telephony/canary",
        "/api/v1/n8n/executions",
        "/api/v1/n8n/executions/register",
        "/api/v1/n8n/acknowledgements",
        "/api/v1/registry/resolve",
        "/api/v1/events",
    }
)
SELF_AUTHENTICATED_PATHS = frozenset({"/v1/registry/search"})
N8N_TRANSITION_PATH = re.compile(
    r"^/api/v1/n8n/executions/[0-9a-fA-F-]{36}/transitions$"
)


@app.middleware("http")
async def control_request_guard(request: Request, call_next):
    if (
        int(request.headers.get("content-length", "0") or 0)
        > settings.request_max_bytes
    ):
        return JSONResponse({"detail": "request too large"}, status_code=413)
    if (
        (request.url.path.startswith("/api/") or request.url.path.startswith("/v1/"))
        and request.url.path not in SIGNED_WEBHOOK_PATHS
        and not (
            request.method == "POST" and N8N_TRANSITION_PATH.fullmatch(request.url.path)
        )
        and request.url.path not in SELF_AUTHENTICATED_PATHS
    ):
        try:
            verify_bearer(
                request.headers.get("Authorization", ""), settings.middleware_secret
            )
        except BearerAuthError as exc:
            status_code = 503 if not settings.middleware_secret else 401
            return JSONResponse({"detail": str(exc)}, status_code=status_code)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = (
        request.headers.get("X-Correlation-ID", "") or "generated"
    )
    return response


@app.get("/healthz")
@app.get("/health")
async def healthz() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": "dry-run",
        "authorization": "online" if settings.auth_ready else "offline",
    }


@app.get("/readyz", response_model=None)
@app.get("/readiness", response_model=None)
async def readyz() -> dict[str, str] | JSONResponse:
    if not settings.auth_ready:
        return JSONResponse(
            {"status": "not-ready", "authorization": "offline"}, status_code=503
        )
    return {"status": "ready", "integration": "outbox-only", "authorization": "online"}


@app.get("/version")
async def version() -> dict[str, str]:
    return {
        "service": "codestra-contact-center-middleware",
        "version": "1.0.0",
        "environment": settings.environment,
    }
