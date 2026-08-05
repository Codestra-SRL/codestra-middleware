"""Deterministic policy and validation for durable AI workforce workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Header, HTTPException

from app.core.config import settings
from app.core.jwt_auth import JWTAuthError, KeycloakValidator

MAX_PLAN_STEPS = 50
MAX_PLAN_DEPTH = 5
MAX_PARALLEL_BRANCHES = 10
MAX_TASKS_PER_WORKFLOW = 250
MAX_DELEGATION_DEPTH = 3
MAX_REPLANS_PER_WORKFLOW = 5
MAX_TOOL_CALLS_PER_TASK = 20
MAX_RETRIES_PER_TASK = 5
MAX_WORKFLOW_RUNTIME_DAYS = 90

PROHIBITED_TOOLS = frozenset(
    {"live_trading", "production_finance", "destructive_delete", "telephony_activate"}
)
ALLOWED_TOOLS = frozenset(
    {
        "odoo_read",
        "n8n_staging",
        "draft_email",
        "calendar_staging",
        "scraper_staging",
        "knowledge_search",
        "qwen_plan",
    }
)

WORKFLOW_TRANSITIONS = {
    "DRAFT": {"VALIDATING", "CANCELLED"},
    "VALIDATING": {"WAITING_FOR_PLAN", "PLAN_REVIEW", "SECURITY_BLOCKED", "FAILED"},
    "WAITING_FOR_PLAN": {"PLAN_REVIEW", "FAILED", "CANCELLED"},
    "PLAN_REVIEW": {"WAITING_FOR_APPROVAL", "SECURITY_BLOCKED", "CANCELLED"},
    "WAITING_FOR_APPROVAL": {"SCHEDULED", "QUEUED", "CANCELLED", "EXPIRED"},
    "SCHEDULED": {"QUEUED", "PAUSED", "CANCELLED", "EXPIRED"},
    "QUEUED": {"RUNNING", "PAUSED", "CANCELLED", "EXPIRED"},
    "RUNNING": {
        "WAITING_FOR_DEPENDENCY",
        "WAITING_FOR_HUMAN",
        "WAITING_FOR_PROVIDER",
        "WAITING_FOR_TIMER",
        "WAITING_FOR_EVENT",
        "PAUSED",
        "BLOCKED",
        "RETRY_SCHEDULED",
        "COMPENSATING",
        "RECONCILIATION_REQUIRED",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "EXPIRED",
        "SECURITY_BLOCKED",
    },
    "WAITING_FOR_DEPENDENCY": {"QUEUED", "BLOCKED", "CANCELLED", "EXPIRED"},
    "WAITING_FOR_HUMAN": {"QUEUED", "BLOCKED", "CANCELLED", "EXPIRED"},
    "WAITING_FOR_PROVIDER": {
        "QUEUED",
        "RETRY_SCHEDULED",
        "BLOCKED",
        "CANCELLED",
        "EXPIRED",
    },
    "WAITING_FOR_TIMER": {"QUEUED", "CANCELLED", "EXPIRED"},
    "WAITING_FOR_EVENT": {"QUEUED", "CANCELLED", "EXPIRED"},
    "PAUSED": {"QUEUED", "CANCELLED", "EXPIRED"},
    "BLOCKED": {
        "QUEUED",
        "PLAN_REVIEW",
        "COMPENSATING",
        "CANCELLED",
        "FAILED",
        "EXPIRED",
    },
    "RETRY_SCHEDULED": {"QUEUED", "BLOCKED", "FAILED", "CANCELLED", "EXPIRED"},
    "COMPENSATING": {"CANCELLED", "FAILED", "RECONCILIATION_REQUIRED"},
    "RECONCILIATION_REQUIRED": {"QUEUED", "COMPLETED", "FAILED", "CANCELLED"},
    "SECURITY_BLOCKED": {"CANCELLED"},
    "COMPLETED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
    "EXPIRED": set(),
}

ROLE_PERMISSIONS = {
    "AI_WORKFLOW_VIEWER": {"read"},
    "AI_WORKFLOW_CREATOR": {"read", "create_goal", "create_plan", "create_workflow"},
    "AI_WORKFLOW_MANAGER": {
        "read",
        "create_goal",
        "create_plan",
        "create_workflow",
        "approve_plan",
        "control",
        "retry",
        "reconcile",
    },
    "AI_WORKFLOW_AUDITOR": {"read", "audit"},
}


@dataclass(frozen=True)
class WorkflowPrincipal:
    subject: str
    tenant_id: str
    workspace_id: str
    employee_id: str
    roles: frozenset[str]

    def require(self, permission: str) -> None:
        if not any(
            permission in ROLE_PERMISSIONS.get(role, set()) for role in self.roles
        ):
            raise HTTPException(403, "AI workflow permission denied")


def _bearer(value: str) -> str:
    scheme, sep, token = value.partition(" ")
    if scheme.lower() != "bearer" or not sep or not token.strip():
        raise HTTPException(401, "bearer authorization required")
    return token.strip()


async def workflow_principal(
    authorization: str = Header(..., alias="Authorization"),
) -> WorkflowPrincipal:
    try:
        claims = KeycloakValidator(
            issuer=settings.keycloak_issuer,
            audience=settings.keycloak_audience,
            jwks_url=settings.keycloak_jwks_url,
            authorized_parties=frozenset(
                x.strip()
                for x in settings.keycloak_authorized_parties.split(",")
                if x.strip()
            ),
        ).validate(_bearer(authorization))
    except (JWTAuthError, ValueError) as exc:
        raise HTTPException(401, "invalid workflow identity") from exc
    values = [
        claims.get(key) for key in ("sub", "tenant_id", "workspace_id", "employee_id")
    ]
    if not all(isinstance(v, str) and v for v in values):
        raise HTTPException(403, "workflow identity scope incomplete")
    roles = set(claims.get("roles", [])) | set(
        claims.get("realm_access", {}).get("roles", [])
    )
    allowed = frozenset(roles).intersection(ROLE_PERMISSIONS)
    if not allowed:
        raise HTTPException(403, "AI workflow role required")
    return WorkflowPrincipal(
        cast(str, values[0]),
        cast(str, values[1]),
        cast(str, values[2]),
        cast(str, values[3]),
        allowed,
    )


def validate_transition(current: str, target: str) -> None:
    if target not in WORKFLOW_TRANSITIONS.get(current, set()):
        raise HTTPException(409, f"invalid workflow transition {current}->{target}")


def validate_plan(
    plan: dict[str, Any], *, tenant_id: str, allowed_employees: set[str]
) -> list[str]:
    errors: list[str] = []
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps or len(steps) > MAX_PLAN_STEPS:
        return ["plan must contain 1..50 steps"]
    ids = [step.get("step_id") for step in steps if isinstance(step, dict)]
    if (
        len(ids) != len(steps)
        or any(not isinstance(item, str) or not item for item in ids)
        or len(set(ids)) != len(ids)
    ):
        errors.append("step IDs must be unique non-empty strings")
    graph: dict[str, list[str]] = {}
    for step in steps:
        step_id = step.get("step_id", "")
        deps = step.get("dependencies", [])
        graph[step_id] = deps if isinstance(deps, list) else []
        if any(dep not in ids for dep in graph[step_id]):
            errors.append(f"{step_id}: missing dependency")
        tools = set(step.get("required_tools", []))
        if tools - ALLOWED_TOOLS or tools & PROHIBITED_TOOLS:
            errors.append(f"{step_id}: unknown or prohibited tool")
        if step.get("assigned_employee") not in allowed_employees:
            errors.append(f"{step_id}: unsupported employee")
        if not step.get("completion_criteria"):
            errors.append(f"{step_id}: completion criteria required")
        if step.get("risk_level") in {"HIGH", "CRITICAL"} and not step.get(
            "approval_requirement"
        ):
            errors.append(f"{step_id}: approval gate required")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append("circular dependency")
            return
        if node in visited:
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    if plan.get("tenant_id", tenant_id) != tenant_id:
        errors.append("cross-tenant plan reference")
    if not plan.get("completion_criteria"):
        errors.append("plan completion criteria required")
    return sorted(set(errors))


def retry_at(attempt: int, *, now: datetime | None = None) -> datetime:
    if attempt < 1 or attempt > MAX_RETRIES_PER_TASK:
        raise ValueError("retry attempt exceeds bounded policy")
    base = min(3600, 30 * 2 ** (attempt - 1))
    deterministic_jitter = (attempt * 17) % 23
    return (now or datetime.now(UTC)) + timedelta(seconds=base + deterministic_jitter)


def validate_schedule(
    timezone: str, maximum_occurrences: int, misfire_policy: str, overlap_policy: str
) -> ZoneInfo:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("IANA timezone required") from exc
    if maximum_occurrences < 1 or maximum_occurrences > 10000:
        raise ValueError("bounded occurrence count required")
    if misfire_policy not in {"SKIP", "RUN_ONCE", "RUN_ALL_MISSED", "REQUIRE_REVIEW"}:
        raise ValueError("invalid misfire policy")
    if overlap_policy not in {
        "ALLOW",
        "SKIP_NEW",
        "CANCEL_OLD",
        "QUEUE_NEW",
        "REQUIRE_REVIEW",
    }:
        raise ValueError("invalid overlap policy")
    return zone
