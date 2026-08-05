"""Data Factory registry and quality control-plane endpoints."""

from typing import Any
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from app.core.config import settings
from app.core.data_factory import IngestionContext, lineage_is_traceable, validate_ingestion

router = APIRouter(prefix="/api/v1/data-factory", tags=["data-factory"])


class IngestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_code: str = Field(min_length=1, max_length=96)
    tenant_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    schema_version: str = Field(min_length=1, max_length=32)
    idempotency_key: str = Field(min_length=8, max_length=255)
    checksum: str = Field(min_length=8, max_length=128)


@router.get("/sources")
async def sources(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not settings.ai_data_factory_enabled:
        raise HTTPException(404, "data factory unavailable")
    if not tenant_id:
        raise HTTPException(403, "tenant scope required")
    return {"tenant_id": tenant_id, "sources": [], "external_exports": False}


@router.post("/ingestion-runs", status_code=202)
async def ingest(body: IngestionRequest) -> dict[str, Any]:
    if not settings.ai_data_factory_staging_enabled:
        raise HTTPException(404, "data factory staging unavailable")
    valid, reason = validate_ingestion(IngestionContext(**body.model_dump()))
    if not valid:
        raise HTTPException(400, reason)
    return {"state": "RECEIVED", "source_code": body.source_code, "published": False, "traceable": lineage_is_traceable(source_reference=body.source_code, ingestion_run=body.idempotency_key, product_reference="staging")}


@router.get("/quality")
async def quality(tenant_id: str = Header("", alias="X-Tenant-ID")) -> dict[str, Any]:
    if not tenant_id:
        raise HTTPException(403, "tenant scope required")
    return {"tenant_id": tenant_id, "quality_state": "STAGING_ONLY", "quarantine_backlog": 0}
