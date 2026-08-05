"""Tenant-scoped logistics API. PostgreSQL is the sole source of truth."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logistics import (
    LogisticsPrincipal,
    logistics_principal,
    request_hash,
    token_digest,
    utcnow,
    validate_transition,
    SHIPMENT_TRANSITIONS,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/logistics", tags=["logistics"])


class OrderIn(BaseModel):
    external_key: str = Field(min_length=3, max_length=128)
    customer_external_key: str = Field(min_length=3, max_length=128)
    pickup_location: dict[str, Any]
    delivery_location: dict[str, Any]
    commodity: str = Field(min_length=1, max_length=200)
    quantity: int = Field(gt=0, le=1000000)
    weight_kg: float = Field(gt=0, le=1000000)


class ShipmentIn(OrderIn):
    order_external_key: str = Field(min_length=3, max_length=128)
    service_level: str = Field(default="STANDARD", max_length=32)


class LoadIn(BaseModel):
    external_key: str = Field(min_length=3, max_length=128)
    shipment_ids: list[str] = Field(default_factory=list, max_length=100)


class StatusIn(BaseModel):
    status: str
    reason: str = Field(default="", max_length=500)


class AssignmentIn(BaseModel):
    external_key: str = Field(min_length=3, max_length=128)


class ProofIn(BaseModel):
    proof_type: str
    object_key: str = Field(pattern=r"^[a-zA-Z0-9/_-]{8,255}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    recipient_name: str = Field(default="", max_length=120)


class ExceptionIn(BaseModel):
    exception_type: str
    note: str = Field(min_length=3, max_length=2000)


class QuoteIn(BaseModel):
    external_key: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    distance_km: float = Field(gt=0)
    weight_kg: float = Field(gt=0)


class ClaimIn(BaseModel):
    external_key: str
    shipment_id: str
    reason: str = Field(min_length=3, max_length=2000)


async def _idempotency(
    db: AsyncSession, p: LogisticsPrincipal, key: str, kind: str, payload: Any
) -> dict[str, Any] | None:
    if len(key) < 16 or len(key) > 255:
        raise HTTPException(400, "valid Idempotency-Key required")
    digest = request_hash(payload)
    row = (
        (
            await db.execute(
                text(
                    "SELECT request_hash,response_json FROM logistics_idempotency WHERE tenant_id=:t AND operation=:o AND idempotency_key=:k"
                ),
                {"t": p.tenant_id, "o": kind, "k": key},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row:
        if row["request_hash"] != digest:
            raise HTTPException(409, "idempotency conflict")
        return row["response_json"]
    return None


async def _save_idempotency(
    db: AsyncSession,
    p: LogisticsPrincipal,
    key: str,
    kind: str,
    payload: Any,
    response: Any,
) -> None:
    await db.execute(
        text(
            "INSERT INTO logistics_idempotency(tenant_id,operation,idempotency_key,request_hash,response_json,expires_at) VALUES(:t,:o,:k,:h,CAST(:r AS jsonb),:e)"
        ),
        {
            "t": p.tenant_id,
            "o": kind,
            "k": key,
            "h": request_hash(payload),
            "r": __import__("json").dumps(response),
            "e": utcnow() + timedelta(days=7),
        },
    )


@router.get("/overview")
async def overview(
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    rows = (
        (
            await db.execute(
                text(
                    "SELECT status,count(*) count FROM logistics_shipments WHERE tenant_id=:t AND workspace_id=:w GROUP BY status"
                ),
                {"t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .all()
    )
    return {
        "shipments_by_status": {r["status"]: r["count"] for r in rows},
        "automatic_dispatch": False,
        "production": False,
    }


@router.post("/orders", status_code=201)
async def create_order(
    body: OrderIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("create_order")
    payload = body.model_dump()
    replay = await _idempotency(db, p, idempotency_key, "create_order", payload)
    if replay:
        return replay
    oid = f"ORD-{uuid4().hex}"
    await db.execute(
        text(
            "INSERT INTO logistics_orders(public_id,tenant_id,workspace_id,external_key,customer_external_key,status,payload_json,created_by) VALUES(:id,:t,:w,:e,:c,'DRAFT',CAST(:p AS jsonb),:s)"
        ),
        {
            "id": oid,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "e": body.external_key,
            "c": body.customer_external_key,
            "p": __import__("json").dumps(payload),
            "s": p.subject,
        },
    )
    result = {"id": oid, "status": "DRAFT"}
    await _save_idempotency(db, p, idempotency_key, "create_order", payload, result)
    await db.commit()
    return result


@router.get("/orders")
async def list_orders(
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    return [
        dict(r)
        for r in (
            await db.execute(
                text(
                    "SELECT public_id,status,external_key,created_at FROM logistics_orders WHERE tenant_id=:t AND workspace_id=:w ORDER BY created_at DESC LIMIT 200"
                ),
                {"t": p.tenant_id, "w": p.workspace_id},
            )
        ).mappings()
    ]


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    row = (
        (
            await db.execute(
                text(
                    "SELECT public_id,status,external_key,customer_external_key,payload_json,created_at FROM logistics_orders WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w"
                ),
                {"i": order_id, "t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "order not found")
    return dict(row)


@router.post("/shipments", status_code=201)
async def create_shipment(
    body: ShipmentIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("create_shipment")
    payload = body.model_dump()
    replay = await _idempotency(db, p, idempotency_key, "create_shipment", payload)
    if replay:
        return replay
    sid = f"SHP-{uuid4().hex}"
    await db.execute(
        text(
            "INSERT INTO logistics_shipments(public_id,tenant_id,workspace_id,external_key,order_external_key,status,payload_json,created_by) VALUES(:id,:t,:w,:e,:o,'CREATED',CAST(:p AS jsonb),:s)"
        ),
        {
            "id": sid,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "e": body.external_key,
            "o": body.order_external_key,
            "p": __import__("json").dumps(payload),
            "s": p.subject,
        },
    )
    result = {"id": sid, "status": "CREATED"}
    await _save_idempotency(db, p, idempotency_key, "create_shipment", payload, result)
    await db.commit()
    return result


@router.get("/shipments")
async def list_shipments(
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    return [
        dict(r)
        for r in (
            await db.execute(
                text(
                    "SELECT public_id,status,external_key,updated_at FROM logistics_shipments WHERE tenant_id=:t AND workspace_id=:w ORDER BY updated_at DESC LIMIT 200"
                ),
                {"t": p.tenant_id, "w": p.workspace_id},
            )
        ).mappings()
    ]


@router.get("/shipments/{shipment_id}")
async def get_shipment(
    shipment_id: str,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    row = (
        (
            await db.execute(
                text(
                    "SELECT public_id,status,external_key,payload_json,updated_at FROM logistics_shipments WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w"
                ),
                {"i": shipment_id, "t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "shipment not found")
    return dict(row)


@router.post("/shipments/{shipment_id}/status")
async def shipment_status(
    shipment_id: str,
    body: StatusIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("driver_status" if "LOGISTICS_DRIVER" in p.roles else "dispatch")
    row = (
        (
            await db.execute(
                text(
                    "SELECT status FROM logistics_shipments WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w FOR UPDATE"
                ),
                {"i": shipment_id, "t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "shipment not found")
    validate_transition(row["status"], body.status, SHIPMENT_TRANSITIONS)
    await db.execute(
        text(
            "UPDATE logistics_shipments SET status=:n,updated_at=now() WHERE public_id=:i"
        ),
        {"n": body.status, "i": shipment_id},
    )
    await db.execute(
        text(
            "INSERT INTO logistics_status_events(tenant_id,workspace_id,shipment_public_id,from_status,to_status,actor_subject,reason,idempotency_key) VALUES(:t,:w,:i,:f,:n,:s,:r,:k) ON CONFLICT DO NOTHING"
        ),
        {
            "t": p.tenant_id,
            "w": p.workspace_id,
            "i": shipment_id,
            "f": row["status"],
            "n": body.status,
            "s": p.subject,
            "r": body.reason,
            "k": idempotency_key,
        },
    )
    await db.commit()
    return {"id": shipment_id, "status": body.status}


@router.post("/loads", status_code=201)
async def create_load(
    body: LoadIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("dispatch")
    lid = f"LOD-{uuid4().hex}"
    await db.execute(
        text(
            "INSERT INTO logistics_loads(public_id,tenant_id,workspace_id,external_key,status,shipment_ids,created_by) VALUES(:i,:t,:w,:e,'DRAFT',CAST(:s AS jsonb),:u)"
        ),
        {
            "i": lid,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "e": body.external_key,
            "s": __import__("json").dumps(body.shipment_ids),
            "u": p.subject,
        },
    )
    await db.commit()
    return {"id": lid, "status": "DRAFT"}


@router.get("/loads")
async def list_loads(
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    return [
        dict(r)
        for r in (
            await db.execute(
                text(
                    "SELECT public_id,status,external_key,driver_external_key,vehicle_external_key FROM logistics_loads WHERE tenant_id=:t AND workspace_id=:w"
                ),
                {"t": p.tenant_id, "w": p.workspace_id},
            )
        ).mappings()
    ]


@router.get("/loads/{load_id}")
async def get_load(
    load_id: str,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    row = (
        (
            await db.execute(
                text(
                    "SELECT * FROM logistics_loads WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w"
                ),
                {"i": load_id, "t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "load not found")
    return dict(row)


async def _assign(
    load_id: str, field: str, value: str, p: LogisticsPrincipal, db: AsyncSession
):
    p.require("dispatch")
    result = await db.execute(
        text(
            f"UPDATE logistics_loads SET {field}=:v,updated_at=now() WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w AND status='DRAFT' RETURNING public_id"
        ),
        {"v": value, "i": load_id, "t": p.tenant_id, "w": p.workspace_id},
    )
    if not result.scalar_one_or_none():
        raise HTTPException(409, "load unavailable for assignment")
    await db.commit()
    return {"id": load_id, field: value}


@router.post("/loads/{load_id}/assign-driver")
async def assign_driver(
    load_id: str,
    body: AssignmentIn,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    return await _assign(load_id, "driver_external_key", body.external_key, p, db)


@router.post("/loads/{load_id}/assign-vehicle")
async def assign_vehicle(
    load_id: str,
    body: AssignmentIn,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    return await _assign(load_id, "vehicle_external_key", body.external_key, p, db)


@router.post("/loads/{load_id}/release")
async def release_load(
    load_id: str,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("dispatch")
    row = (
        await db.execute(
            text(
                "UPDATE logistics_loads SET status='RELEASED',updated_at=now() WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w AND status='DRAFT' AND driver_external_key IS NOT NULL AND vehicle_external_key IS NOT NULL RETURNING public_id"
            ),
            {"i": load_id, "t": p.tenant_id, "w": p.workspace_id},
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(409, "complete assignments required")
    await db.commit()
    return {"id": load_id, "status": "RELEASED"}


@router.post("/shipments/{shipment_id}/exception", status_code=201)
async def create_exception(
    shipment_id: str,
    body: ExceptionIn,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("exception")
    eid = f"EXC-{uuid4().hex}"
    await db.execute(
        text(
            "INSERT INTO logistics_exceptions(public_id,tenant_id,workspace_id,shipment_public_id,exception_type,status,note,created_by) SELECT :e,:t,:w,public_id,:x,'OPEN',:n,:u FROM logistics_shipments WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w"
        ),
        {
            "e": eid,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "i": shipment_id,
            "x": body.exception_type,
            "n": body.note,
            "u": p.subject,
        },
    )
    await db.commit()
    return {"id": eid, "status": "OPEN"}


@router.post("/shipments/{shipment_id}/proof", status_code=201)
async def create_proof(
    shipment_id: str,
    body: ProofIn,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("proof")
    pid = f"PRF-{uuid4().hex}"
    await db.execute(
        text(
            "INSERT INTO logistics_proof_events(public_id,tenant_id,workspace_id,shipment_public_id,proof_type,object_key,content_sha256,recipient_name,created_by) VALUES(:i,:t,:w,:s,:p,:o,:h,:r,:u)"
        ),
        {
            "i": pid,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "s": shipment_id,
            "p": body.proof_type,
            "o": body.object_key,
            "h": body.sha256,
            "r": body.recipient_name,
            "u": p.subject,
        },
    )
    await db.commit()
    return {"id": pid, "scan_status": "PENDING"}


@router.post("/quotes", status_code=201)
async def create_quote(
    body: QuoteIn,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("quote")
    qid = f"QTE-{uuid4().hex}"
    amount = round(75 + body.distance_km * 1.25 + body.weight_kg * 0.05, 2)
    await db.execute(
        text(
            "INSERT INTO logistics_quotes(public_id,tenant_id,workspace_id,external_key,status,currency,amount,calculation_version,created_by) VALUES(:i,:t,:w,:e,'REVIEW_REQUIRED',:c,:a,'mock-rate-v1',:u)"
        ),
        {
            "i": qid,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "e": body.external_key,
            "c": body.currency,
            "a": amount,
            "u": p.subject,
        },
    )
    await db.commit()
    return {"id": qid, "status": "REVIEW_REQUIRED", "amount": amount, "binding": False}


@router.get("/quotes/{quote_id}")
async def get_quote(
    quote_id: str,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    row = (
        (
            await db.execute(
                text(
                    "SELECT public_id,status,currency,amount,calculation_version FROM logistics_quotes WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w"
                ),
                {"i": quote_id, "t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "quote not found")
    return dict(row)


@router.get("/tracking/{tracking_token}")
async def public_tracking(tracking_token: str, db: AsyncSession = Depends(get_session)):
    if len(tracking_token) < 32:
        raise HTTPException(404, "tracking not found")
    row = (
        (
            await db.execute(
                text(
                    "SELECT s.public_id,s.status,s.payload_json->'pickup_location'->>'city' origin_city,s.payload_json->'delivery_location'->>'city' destination_city FROM logistics_tracking_tokens t JOIN logistics_shipments s ON s.public_id=t.shipment_public_id AND s.tenant_id=t.tenant_id WHERE t.token_digest=:d AND t.revoked_at IS NULL AND t.expires_at>now()"
                ),
                {"d": token_digest(tracking_token)},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "tracking not found")
    return dict(row)


@router.post("/claims", status_code=201)
async def create_claim(
    body: ClaimIn,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("create_claim")
    cid = f"CLM-{uuid4().hex}"
    await db.execute(
        text(
            "INSERT INTO logistics_claims(public_id,tenant_id,workspace_id,external_key,shipment_public_id,status,reason,created_by) VALUES(:i,:t,:w,:e,:s,'SUBMITTED',:r,:u)"
        ),
        {
            "i": cid,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "e": body.external_key,
            "s": body.shipment_id,
            "r": body.reason,
            "u": p.subject,
        },
    )
    await db.commit()
    return {"id": cid, "status": "SUBMITTED", "human_review_required": True}


@router.get("/claims/{claim_id}")
async def get_claim(
    claim_id: str,
    p: LogisticsPrincipal = Depends(logistics_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    row = (
        (
            await db.execute(
                text(
                    "SELECT public_id,status,shipment_public_id,reason FROM logistics_claims WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w"
                ),
                {"i": claim_id, "t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "claim not found")
    return dict(row)
