"""Private Controller API ASGI entrypoint.

This entrypoint is intentionally separate from ``app.main`` so controller
routes cannot appear on the public Middleware listener by importing a router.
Deployment must bind this app only to the approved private address.
"""

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.controller import controller, router
from app.core.config import settings
from app.db.session import get_session

app = FastAPI(title="Codestra Private Controller", version="1.0.0")
app.include_router(router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "exposure": "private-only"}


@app.get("/readyz", response_model=None)
async def readyz(session: AsyncSession = Depends(get_session)) -> dict[str, str] | JSONResponse:
    if not settings.controller_private_enabled:
        return JSONResponse({"status": "not-ready", "reason": "disabled"}, status_code=503)
    try:
        controller()
        if settings.controller_repository_backend.strip().lower() != "postgres":
            raise RuntimeError("PostgreSQL repository required")
        await session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            {"status": "not-ready", "reason": "signing-authority-unavailable"},
            status_code=503,
        )
    return {"status": "ready", "exposure": "private-only"}
