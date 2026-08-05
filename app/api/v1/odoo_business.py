"""Authenticated Wave 3 business API backed by durable Odoo commands."""

import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.identity import _identity
from app.core.iam import IAMAuthorizationError
from app.core.odoo_business import (
    BusinessCommand,
    OdooBusinessError,
    RESOURCE_TYPES,
    payload_hash,
    scoped_idempotency_hash,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/business", tags=["odoo-business-integration"])


class CommandRequest(BaseModel):
    resource_type: str = Field(min_length=2, max_length=64)
    operation: str = Field(pattern=r"^(create|update|archive|link|transition)$")
    resource_key: str = Field(min_length=1, max_length=128)
    payload: dict[str, object]
    expected_version: int | None = Field(default=None, ge=1)
    causation_id: str | None = Field(default=None, max_length=128)
    max_attempts: int = Field(default=5, ge=1, le=10)


class ApprovalRequest(BaseModel):
    decision: str = Field(pattern=r"^(APPROVED|REJECTED)$")
    reason: str = Field(min_length=8, max_length=512)


class ReconciliationRequest(BaseModel):
    resource_type: str = Field(min_length=2, max_length=64)
    resource_key: str = Field(min_length=1, max_length=128)
    expected_checksum: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")


def _context(authorization: str, permission: str):
    identity = _identity(authorization)
    try:
        identity.require_permission(permission)
        UUID(identity.tenant_id)
        UUID(identity.workspace_id)
    except (IAMAuthorizationError, ValueError) as exc:
        raise HTTPException(403, "business scope denied") from exc
    return identity


@router.get("/resource-types")
async def resource_types(authorization: str = Header("", alias="Authorization")):
    _context(authorization, "business.read")
    return {"items": sorted(RESOURCE_TYPES), "odoo_is_system_of_record": True}


@router.post("/commands", status_code=202)
async def create_command(
    body: CommandRequest,
    authorization: str = Header("", alias="Authorization"),
    idempotency_key: str = Header("", alias="Idempotency-Key"),
    correlation_id: str = Header("", alias="X-Correlation-ID"),
    db: AsyncSession = Depends(get_session),
):
    identity = _context(authorization, "business.write")
    command = BusinessCommand(
        resource_type=body.resource_type,
        operation=body.operation,  # type: ignore[arg-type]
        resource_key=body.resource_key,
        payload=body.payload,
        expected_version=body.expected_version,
    )
    try:
        command.validate()
        key_hash = scoped_idempotency_hash(
            identity.tenant_id, identity.workspace_id, body.resource_type, idempotency_key
        )
    except OdooBusinessError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not correlation_id or len(correlation_id) > 128:
        raise HTTPException(422, "correlation ID required")
    command_id, public_id = uuid4(), uuid4()
    approval = "PENDING" if command.approval_required else "NOT_REQUIRED"
    state = "APPROVAL_REQUIRED" if command.approval_required else "READY"
    try:
        await db.execute(text("""
            INSERT INTO odoo_business_command (
                id,public_id,tenant_id,workspace_id,resource_type,operation,
                resource_key,expected_version,payload,payload_hash,idempotency_key_hash,
                correlation_id,causation_id,approval_state,state,delivery_mode,
                max_attempts,created_by,updated_by
            ) VALUES (
                :id,:public_id,:tenant,:workspace,:resource_type,:operation,
                :resource_key,:expected_version,CAST(:payload AS jsonb),:payload_hash,
                :key_hash,:correlation,:causation,:approval,:state,'DISABLED',
                :max_attempts,:actor,:actor
            )
        """), {
            "id": command_id, "public_id": public_id, "tenant": UUID(identity.tenant_id),
            "workspace": UUID(identity.workspace_id), "resource_type": body.resource_type,
            "operation": body.operation, "resource_key": body.resource_key,
            "expected_version": body.expected_version,
            "payload": json.dumps(body.payload, sort_keys=True, separators=(",", ":")),
            "payload_hash": payload_hash(body.payload), "key_hash": key_hash,
            "correlation": correlation_id, "causation": body.causation_id,
            "approval": approval, "state": state, "max_attempts": body.max_attempts,
            "actor": identity.subject,
        })
        await db.execute(text("""
            INSERT INTO odoo_business_audit (
                tenant_id,workspace_id,command_id,action,actor,correlation_id,metadata
            ) VALUES (:tenant,:workspace,:command,'COMMAND_CREATED',:actor,:correlation,
                jsonb_build_object('resource_type',CAST(:resource_type AS text),
                                   'operation',CAST(:operation AS text)))
        """), {"tenant": UUID(identity.tenant_id), "workspace": UUID(identity.workspace_id),
                 "command": command_id, "actor": identity.subject,
                 "correlation": correlation_id, "resource_type": body.resource_type,
                 "operation": body.operation})
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = (await db.execute(text("""
            SELECT public_id,state,approval_state,payload_hash FROM odoo_business_command
            WHERE tenant_id=:tenant AND workspace_id=:workspace
              AND resource_type=:resource_type AND idempotency_key_hash=:key_hash
        """), {"tenant": UUID(identity.tenant_id), "workspace": UUID(identity.workspace_id),
                 "resource_type": body.resource_type, "key_hash": key_hash})).mappings().one_or_none()
        if existing is None or existing["payload_hash"] != payload_hash(body.payload):
            raise HTTPException(409, "idempotency key conflict")
        return {"command_id": str(existing["public_id"]), "state": existing["state"],
                "approval_state": existing["approval_state"], "idempotent_replay": True,
                "delivery_mode": "DISABLED"}
    return {"command_id": str(public_id), "state": state, "approval_state": approval,
            "idempotent_replay": False, "delivery_mode": "DISABLED"}


@router.get("/commands")
async def list_commands(
    authorization: str = Header("", alias="Authorization"),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_session),
):
    identity = _context(authorization, "business.read")
    rows = (await db.execute(text("""
        SELECT public_id,resource_type,operation,resource_key,payload_hash,
               approval_state,state,delivery_mode,attempt_count,max_attempts,
               correlation_id,created_at,updated_at,version
        FROM odoo_business_command
        WHERE tenant_id=:tenant AND workspace_id=:workspace
        ORDER BY created_at DESC,id DESC LIMIT :limit
    """), {"tenant": UUID(identity.tenant_id), "workspace": UUID(identity.workspace_id),
             "limit": limit})).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/commands/{command_id}")
async def get_command(
    command_id: UUID,
    authorization: str = Header("", alias="Authorization"),
    db: AsyncSession = Depends(get_session),
):
    identity = _context(authorization, "business.read")
    row = (await db.execute(text("""
        SELECT public_id,resource_type,operation,resource_key,payload_hash,
               approval_state,state,delivery_mode,attempt_count,max_attempts,
               correlation_id,created_at,updated_at,version
        FROM odoo_business_command WHERE public_id=:id
          AND tenant_id=:tenant AND workspace_id=:workspace
    """), {"id": command_id, "tenant": UUID(identity.tenant_id),
             "workspace": UUID(identity.workspace_id)})).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "command not found")
    return dict(row)


@router.post("/commands/{command_id}/approval")
async def approve_command(
    command_id: UUID, body: ApprovalRequest,
    authorization: str = Header("", alias="Authorization"),
    correlation_id: str = Header("", alias="X-Correlation-ID"),
    db: AsyncSession = Depends(get_session),
):
    identity = _context(authorization, "business.approve")
    state = "READY" if body.decision == "APPROVED" else "CANCELLED"
    result = await db.execute(text("""
        UPDATE odoo_business_command SET approval_state=:decision,state=:state,
            approved_by=:actor,approved_at=now(),updated_by=:actor
        WHERE public_id=:id AND tenant_id=:tenant AND workspace_id=:workspace
          AND approval_state='PENDING' AND state='APPROVAL_REQUIRED'
        RETURNING id
    """), {"decision": body.decision, "state": state, "actor": identity.subject,
             "id": command_id, "tenant": UUID(identity.tenant_id),
             "workspace": UUID(identity.workspace_id)})
    internal_id = result.scalar_one_or_none()
    if internal_id is None:
        await db.rollback()
        raise HTTPException(409, "command is not awaiting approval")
    await db.execute(text("""
        INSERT INTO odoo_business_audit
          (tenant_id,workspace_id,command_id,action,actor,correlation_id,metadata)
        VALUES (:tenant,:workspace,:command,:action,:actor,:correlation,
                jsonb_build_object('reason_length',CAST(:reason_length AS integer)))
    """), {"tenant": UUID(identity.tenant_id), "workspace": UUID(identity.workspace_id),
             "command": internal_id, "action": f"COMMAND_{body.decision}",
             "actor": identity.subject, "correlation": correlation_id or "generated",
             "reason_length": len(body.reason)})
    await db.commit()
    return {"command_id": str(command_id), "state": state, "approval_state": body.decision}


@router.post("/commands/{command_id}/cancel", status_code=202)
async def cancel_command(
    command_id: UUID,
    authorization: str = Header("", alias="Authorization"),
    db: AsyncSession = Depends(get_session),
):
    identity = _context(authorization, "business.write")
    row = (await db.execute(text("""
        UPDATE odoo_business_command
        SET cancel_requested_at=now(),
            state=CASE WHEN state IN ('PENDING','APPROVAL_REQUIRED','READY','RETRY_WAIT')
                       THEN 'CANCELLED' ELSE state END,
            updated_by=:actor
        WHERE public_id=:id AND tenant_id=:tenant AND workspace_id=:workspace
          AND state NOT IN ('SUCCEEDED','FAILED','DEAD_LETTER','CANCELLED')
        RETURNING id,state,correlation_id
    """), {"actor": identity.subject, "id": command_id,
             "tenant": UUID(identity.tenant_id),
             "workspace": UUID(identity.workspace_id)})).mappings().one_or_none()
    if row is None:
        await db.rollback()
        raise HTTPException(409, "command cannot be cancelled")
    await db.execute(text("""
        INSERT INTO odoo_business_audit
          (tenant_id,workspace_id,command_id,action,actor,correlation_id,metadata)
        VALUES (:tenant,:workspace,:command,'COMMAND_CANCEL_REQUESTED',:actor,
                :correlation,'{}'::jsonb)
    """), {"tenant": UUID(identity.tenant_id), "workspace": UUID(identity.workspace_id),
             "command": row["id"], "actor": identity.subject,
             "correlation": row["correlation_id"]})
    await db.commit()
    return {"command_id": str(command_id), "state": row["state"], "cancel_requested": True}


@router.post("/reconciliations", status_code=202)
async def create_reconciliation(
    body: ReconciliationRequest,
    authorization: str = Header("", alias="Authorization"),
    correlation_id: str = Header("", alias="X-Correlation-ID"),
    db: AsyncSession = Depends(get_session),
):
    identity = _context(authorization, "business.reconcile")
    if body.resource_type not in RESOURCE_TYPES:
        raise HTTPException(422, "resource type unsupported")
    reconciliation_id = uuid4()
    try:
        await db.execute(text("""
            INSERT INTO odoo_business_reconciliation (
                id,tenant_id,workspace_id,resource_type,resource_key,expected_checksum,
                created_by,updated_by
            ) VALUES (:id,:tenant,:workspace,:resource_type,:resource_key,
                      :expected_checksum,:actor,:actor)
        """), {"id": reconciliation_id, "tenant": UUID(identity.tenant_id),
                 "workspace": UUID(identity.workspace_id), "resource_type": body.resource_type,
                 "resource_key": body.resource_key, "expected_checksum": body.expected_checksum,
                 "actor": identity.subject})
        await db.execute(text("""
            INSERT INTO odoo_business_audit
              (tenant_id,workspace_id,reconciliation_id,action,actor,correlation_id,metadata)
            VALUES (:tenant,:workspace,:id,'RECONCILIATION_REQUESTED',:actor,
                    :correlation,jsonb_build_object('resource_type',CAST(:resource_type AS text)))
        """), {"tenant": UUID(identity.tenant_id), "workspace": UUID(identity.workspace_id),
                 "id": reconciliation_id, "actor": identity.subject,
                 "correlation": correlation_id or "generated",
                 "resource_type": body.resource_type})
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "reconciliation already pending") from exc
    return {"reconciliation_id": str(reconciliation_id), "state": "PENDING",
            "external_read_enabled": False, "correlation_id": correlation_id or "generated"}
