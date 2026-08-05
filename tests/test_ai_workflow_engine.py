from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.core.ai_workflows import (
    MAX_RETRIES_PER_TASK,
    WorkflowPrincipal,
    retry_at,
    validate_plan,
    validate_schedule,
    validate_transition,
)
from app.core.workflow_conditions import evaluate


def valid_plan():
    return {
        "goal_id": "GOAL-SYN",
        "summary": "Synthetic support plan",
        "assumptions": [],
        "required_information": [],
        "tenant_id": "tenant-a",
        "steps": [
            {
                "step_id": "classify",
                "title": "Classify",
                "description": "Classify synthetic ticket",
                "assigned_employee": "employee-a",
                "dependencies": [],
                "required_tools": ["knowledge_search"],
                "required_permissions": ["support.read"],
                "approval_requirement": "",
                "risk_level": "LOW",
                "estimated_cost": 1,
                "deadline": None,
                "completion_criteria": ["classification recorded"],
            },
            {
                "step_id": "draft",
                "title": "Draft",
                "description": "Draft response",
                "assigned_employee": "employee-a",
                "dependencies": ["classify"],
                "required_tools": ["draft_email"],
                "required_permissions": ["support.draft"],
                "approval_requirement": "human_support_approval",
                "risk_level": "HIGH",
                "estimated_cost": 2,
                "deadline": None,
                "completion_criteria": ["draft created"],
            },
        ],
        "approval_points": ["human_support_approval"],
        "risks": [],
        "fallbacks": [],
        "completion_criteria": ["human-reviewed draft ready"],
        "escalation_conditions": [],
    }


def test_valid_plan_and_bounded_tools_pass():
    assert (
        validate_plan(
            valid_plan(), tenant_id="tenant-a", allowed_employees={"employee-a"}
        )
        == []
    )


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (
            lambda p: p["steps"][0].update(required_tools=["live_trading"]),
            "unknown or prohibited tool",
        ),
        (
            lambda p: p["steps"][0].update(assigned_employee="other"),
            "unsupported employee",
        ),
        (lambda p: p.update(tenant_id="tenant-b"), "cross-tenant"),
    ],
)
def test_prohibited_plan_shapes_fail_closed(mutation, expected):
    plan = valid_plan()
    mutation(plan)
    assert any(
        expected in item
        for item in validate_plan(
            plan, tenant_id="tenant-a", allowed_employees={"employee-a"}
        )
    )


def test_circular_dependencies_never_execute():
    plan = valid_plan()
    plan["steps"][0]["dependencies"] = ["draft"]
    assert "circular dependency" in validate_plan(
        plan, tenant_id="tenant-a", allowed_employees={"employee-a"}
    )


def test_transitions_require_declared_edge_and_state_version_is_api_required():
    validate_transition("RUNNING", "WAITING_FOR_HUMAN")
    with pytest.raises(HTTPException):
        validate_transition("DRAFT", "COMPLETED")


def test_retry_is_bounded_and_deterministic():
    now = datetime(2026, 8, 4, tzinfo=UTC)
    assert retry_at(1, now=now) > now
    with pytest.raises(ValueError):
        retry_at(MAX_RETRIES_PER_TASK + 1, now=now)


def test_schedule_requires_explicit_iana_timezone_and_bounded_occurrences():
    assert (
        validate_schedule("America/Santo_Domingo", 10, "RUN_ONCE", "QUEUE_NEW").key
        == "America/Santo_Domingo"
    )
    with pytest.raises(ValueError):
        validate_schedule("Server/Local", 10, "RUN_ONCE", "QUEUE_NEW")
    with pytest.raises(ValueError):
        validate_schedule("UTC", 0, "RUN_ONCE", "QUEUE_NEW")


def test_condition_language_rejects_code_and_unknown_fields():
    assert evaluate(
        {"field": "status", "operator": "eq", "value": "QUALIFIED"},
        {"status": "QUALIFIED"},
    )
    with pytest.raises(ValueError):
        evaluate({"field": "__class__", "operator": "eq", "value": "x"}, {})


def test_ai_employee_cannot_self_approve_or_control_without_manager_role():
    creator = WorkflowPrincipal(
        "u", "tenant", "workspace", "employee", frozenset({"AI_WORKFLOW_CREATOR"})
    )
    creator.require("create_plan")
    for permission in ("approve_plan", "control", "reconcile"):
        with pytest.raises(HTTPException):
            creator.require(permission)
