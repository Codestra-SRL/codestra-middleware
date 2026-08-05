"""Durable AI Workforce control-plane API."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_workflows import (
    WorkflowPrincipal,
    validate_plan,
    validate_transition,
    workflow_principal,
)
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/ai-workforce", tags=["ai-workflows"])


class GoalIn(BaseModel):
    external_key: str = Field(min_length=8, max_length=128)
    goal_type: Literal[
        "ONE_TIME",
        "RECURRING",
        "EVENT_DRIVEN",
        "CONDITION_DRIVEN",
        "PROJECT",
        "CAMPAIGN",
        "CASE",
        "SERVICE_REQUEST",
        "INCIDENT_RESPONSE",
    ]
    desired_outcome: str = Field(min_length=10, max_length=4000)
    business_owner: str = Field(min_length=3, max_length=128)
    ai_employee_owner: str = Field(min_length=3, max_length=128)
    deadline: datetime
    priority: Literal["LOW", "NORMAL", "HIGH", "CRITICAL"] = "NORMAL"
    allowed_tools: list[str] = Field(max_length=20)
    approval_requirements: list[str]
    budget_limit: float = Field(ge=0, le=1000000)
    token_limit: int = Field(ge=0, le=10000000)
    completion_criteria: list[str] = Field(min_length=1, max_length=20)
    prohibited_outcomes: list[str] = Field(min_length=1, max_length=20)
    escalation_route: str = Field(min_length=3, max_length=128)


class PlanIn(BaseModel):
    goal_id: str
    plan: dict[str, Any]
    allowed_employees: list[str] = Field(min_length=1, max_length=50)


class WorkflowIn(BaseModel):
    external_key: str = Field(min_length=8, max_length=128)
    definition_id: str
    definition_version: int = Field(ge=1)
    goal_id: str
    assigned_employee_id: str
    manager_employee_id: str
    priority: Literal["LOW", "NORMAL", "HIGH", "CRITICAL"] = "NORMAL"
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    budget_limit: float = Field(ge=0, le=1000000)
    token_limit: int = Field(ge=0, le=10000000)
    tool_limit: int = Field(ge=0, le=5000)
    task_limit: int = Field(ge=1, le=250)
    due_at: datetime


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def _replay(
    db: AsyncSession, p: WorkflowPrincipal, key: str, operation: str, payload: Any
) -> dict[str, Any] | None:
    if len(key) < 16 or len(key) > 255:
        raise HTTPException(400, "valid Idempotency-Key required")
    row = (
        (
            await db.execute(
                text(
                    "SELECT request_hash,response_json FROM ai_workflow_idempotency WHERE tenant_id=:t AND operation=:o AND idempotency_key=:k"
                ),
                {"t": p.tenant_id, "o": operation, "k": key},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row and row["request_hash"] != _hash(payload):
        raise HTTPException(409, "idempotency conflict")
    return row["response_json"] if row else None


async def _save(
    db: AsyncSession,
    p: WorkflowPrincipal,
    key: str,
    operation: str,
    payload: Any,
    response: Any,
) -> None:
    await db.execute(
        text(
            "INSERT INTO ai_workflow_idempotency(tenant_id,operation,idempotency_key,request_hash,response_json,expires_at) VALUES(:t,:o,:k,:h,CAST(:r AS jsonb),now()+interval '90 days')"
        ),
        {
            "t": p.tenant_id,
            "o": operation,
            "k": key,
            "h": _hash(payload),
            "r": json.dumps(response),
        },
    )


@router.post("/goals", status_code=201)
async def create_goal(
    body: GoalIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("create_goal")
    payload = body.model_dump()
    replay = await _replay(db, p, idempotency_key, "create_goal", payload)
    if replay:
        return replay
    gid = f"GOAL-{uuid4().hex}"
    await db.execute(
        text(
            "INSERT INTO ai_goals(public_id,tenant_id,workspace_id,external_key,goal_type,status,desired_outcome,business_owner,ai_employee_owner,deadline,priority,policy_json,created_by) VALUES(:i,:t,:w,:e,:g,'DRAFT',:d,:b,:a,:x,:p,CAST(:j AS jsonb),:s)"
        ),
        {
            "i": gid,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "e": body.external_key,
            "g": body.goal_type,
            "d": body.desired_outcome,
            "b": body.business_owner,
            "a": body.ai_employee_owner,
            "x": body.deadline,
            "p": body.priority,
            "j": json.dumps(payload, default=str),
            "s": p.subject,
        },
    )
    result = {"id": gid, "status": "DRAFT"}
    await _save(db, p, idempotency_key, "create_goal", payload, result)
    await db.commit()
    return result


@router.get("/goals")
async def list_goals(
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    return [
        dict(row)
        for row in (
            await db.execute(
                text(
                    "SELECT public_id,goal_type,status,desired_outcome,deadline,priority FROM ai_goals WHERE tenant_id=:t AND workspace_id=:w ORDER BY created_at DESC LIMIT 200"
                ),
                {"t": p.tenant_id, "w": p.workspace_id},
            )
        ).mappings()
    ]


@router.get("/goals/{goal_id}")
async def get_goal(
    goal_id: str,
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    row = (
        (
            await db.execute(
                text(
                    "SELECT public_id,goal_type,status,desired_outcome,business_owner,ai_employee_owner,deadline,priority,policy_json FROM ai_goals WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w"
                ),
                {"i": goal_id, "t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "goal not found")
    return dict(row)


@router.post("/plans", status_code=201)
async def create_plan(
    body: PlanIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("create_plan")
    errors = validate_plan(
        body.plan, tenant_id=p.tenant_id, allowed_employees=set(body.allowed_employees)
    )
    if errors:
        raise HTTPException(422, {"validation_errors": errors})
    pid = f"PLAN-{uuid4().hex}"
    await db.execute(
        text(
            "INSERT INTO ai_plans(public_id,tenant_id,workspace_id,goal_public_id,status,plan_json,plan_hash,created_by) VALUES(:i,:t,:w,:g,'PLAN_REVIEW',CAST(:j AS jsonb),:h,:s)"
        ),
        {
            "i": pid,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "g": body.goal_id,
            "j": json.dumps(body.plan),
            "h": _hash(body.plan),
            "s": p.subject,
        },
    )
    await db.commit()
    return {"id": pid, "status": "PLAN_REVIEW", "plan_hash": _hash(body.plan)}


@router.get("/plans/{plan_id}")
async def get_plan(
    plan_id: str,
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    row = (
        (
            await db.execute(
                text(
                    "SELECT public_id,goal_public_id,status,plan_json,plan_hash,version FROM ai_plans WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w"
                ),
                {"i": plan_id, "t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "plan not found")
    return dict(row)


async def _plan_decision(
    plan_id: str, status: str, p: WorkflowPrincipal, db: AsyncSession
):
    p.require("approve_plan")
    row = (
        await db.execute(
            text(
                "UPDATE ai_plans SET status=:s,reviewed_by=:u,reviewed_at=now() WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w AND status='PLAN_REVIEW' RETURNING public_id"
            ),
            {
                "s": status,
                "u": p.subject,
                "i": plan_id,
                "t": p.tenant_id,
                "w": p.workspace_id,
            },
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(409, "plan is not reviewable")
    await db.commit()
    return {"id": plan_id, "status": status}


@router.post("/plans/{plan_id}/approve")
async def approve_plan(
    plan_id: str,
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    return await _plan_decision(plan_id, "APPROVED", p, db)


@router.post("/plans/{plan_id}/reject")
async def reject_plan(
    plan_id: str,
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    return await _plan_decision(plan_id, "REJECTED", p, db)


@router.post("/workflows", status_code=201)
async def create_workflow(
    body: WorkflowIn,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("create_workflow")
    payload = body.model_dump()
    replay = await _replay(db, p, idempotency_key, "create_workflow", payload)
    if replay:
        return replay
    wid = f"WF-{uuid4().hex}"
    await db.execute(
        text(
            "INSERT INTO ai_workflow_instances(public_id,workflow_definition_id,workflow_version,tenant_id,workspace_id,goal_public_id,initiated_by,assigned_employee_id,manager_employee_id,status,priority,risk_level,budget_limit,token_limit,tool_limit,task_limit,due_at,current_step,state_version,trace_id) VALUES(:i,:d,:v,:t,:w,:g,:u,:a,:m,'DRAFT',:p,:r,:b,:n,:l,:k,:x,'',1,:z)"
        ),
        {
            "i": wid,
            "d": body.definition_id,
            "v": body.definition_version,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "g": body.goal_id,
            "u": p.subject,
            "a": body.assigned_employee_id,
            "m": body.manager_employee_id,
            "p": body.priority,
            "r": body.risk_level,
            "b": body.budget_limit,
            "n": body.token_limit,
            "l": body.tool_limit,
            "k": body.task_limit,
            "x": body.due_at,
            "z": uuid4().hex,
        },
    )
    result = {"id": wid, "status": "DRAFT", "state_version": 1}
    await _save(db, p, idempotency_key, "create_workflow", payload, result)
    await db.commit()
    return result


@router.get("/workflows")
async def list_workflows(
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    return [
        dict(row)
        for row in (
            await db.execute(
                text(
                    "SELECT public_id,status,priority,risk_level,due_at,current_step,state_version FROM ai_workflow_instances WHERE tenant_id=:t AND workspace_id=:w ORDER BY created_at DESC LIMIT 200"
                ),
                {"t": p.tenant_id, "w": p.workspace_id},
            )
        ).mappings()
    ]


@router.get("/workflows/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("read")
    row = (
        (
            await db.execute(
                text(
                    "SELECT * FROM ai_workflow_instances WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w"
                ),
                {"i": workflow_id, "t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "workflow not found")
    return dict(row)


async def _control(
    workflow_id: str,
    target: str,
    expected_version: int,
    p: WorkflowPrincipal,
    db: AsyncSession,
):
    p.require("control")
    row = (
        (
            await db.execute(
                text(
                    "SELECT status,state_version FROM ai_workflow_instances WHERE public_id=:i AND tenant_id=:t AND workspace_id=:w FOR UPDATE"
                ),
                {"i": workflow_id, "t": p.tenant_id, "w": p.workspace_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "workflow not found")
    if row["state_version"] != expected_version:
        raise HTTPException(409, "stale workflow state version")
    validate_transition(row["status"], target)
    new_version = expected_version + 1
    await db.execute(
        text(
            "UPDATE ai_workflow_instances SET status=:s,state_version=:v,updated_at=now() WHERE public_id=:i"
        ),
        {"s": target, "v": new_version, "i": workflow_id},
    )
    await db.execute(
        text(
            "INSERT INTO ai_workflow_state_transitions(workflow_public_id,tenant_id,workspace_id,from_status,to_status,from_version,to_version,actor_subject) VALUES(:i,:t,:w,:f,:s,:a,:b,:u)"
        ),
        {
            "i": workflow_id,
            "t": p.tenant_id,
            "w": p.workspace_id,
            "f": row["status"],
            "s": target,
            "a": expected_version,
            "b": new_version,
            "u": p.subject,
        },
    )
    await db.commit()
    return {"id": workflow_id, "status": target, "state_version": new_version}


@router.post("/workflows/{workflow_id}/pause")
async def pause(
    workflow_id: str,
    expected_version: int = Header(..., alias="If-Match-State-Version"),
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    return await _control(workflow_id, "PAUSED", expected_version, p, db)


@router.post("/workflows/{workflow_id}/resume")
async def resume(
    workflow_id: str,
    expected_version: int = Header(..., alias="If-Match-State-Version"),
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    return await _control(workflow_id, "QUEUED", expected_version, p, db)


@router.post("/workflows/{workflow_id}/cancel")
async def cancel(
    workflow_id: str,
    expected_version: int = Header(..., alias="If-Match-State-Version"),
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    return await _control(workflow_id, "CANCELLED", expected_version, p, db)


@router.post("/workflows/{workflow_id}/retry")
async def retry(
    workflow_id: str,
    expected_version: int = Header(..., alias="If-Match-State-Version"),
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("retry")
    return await _control(workflow_id, "QUEUED", expected_version, p, db)


@router.post("/workflows/{workflow_id}/replan")
async def replan(
    workflow_id: str,
    expected_version: int = Header(..., alias="If-Match-State-Version"),
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    return await _control(workflow_id, "PLAN_REVIEW", expected_version, p, db)


@router.post("/workflows/{workflow_id}/reconcile")
async def reconcile(
    workflow_id: str,
    expected_version: int = Header(..., alias="If-Match-State-Version"),
    p: WorkflowPrincipal = Depends(workflow_principal),
    db: AsyncSession = Depends(get_session),
):
    p.require("reconcile")
    return await _control(workflow_id, "QUEUED", expected_version, p, db)
