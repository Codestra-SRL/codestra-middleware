from fastapi import FastAPI
from app.api.v1.events import router as events_router
from app.api.v1.control import router as control_router
from app.api.v1.automation import router as automation_router
from app.api.v1.reports import router as reports_router
from app.core.config import settings
from app.core.auth import BearerAuthError, verify_bearer
from fastapi import Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Codestra Middleware", version="0.2.0")
app.include_router(events_router)
app.include_router(control_router)
app.include_router(automation_router)
app.include_router(reports_router)

SIGNED_WEBHOOK_PATHS = frozenset(
    {
        "/api/v1/events/vicidial",
        "/api/v1/automation/events",
    }
)


@app.middleware("http")
async def control_request_guard(request: Request, call_next):
    if (
        int(request.headers.get("content-length", "0") or 0)
        > settings.request_max_bytes
    ):
        return JSONResponse({"detail": "request too large"}, status_code=413)
    if (
        request.url.path.startswith("/api/")
        and request.url.path not in SIGNED_WEBHOOK_PATHS
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
