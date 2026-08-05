from pathlib import Path

from app.core.config import Settings
from app.main import AI_WORKFLOW_JWT_PATH

ROOT = Path(__file__).parents[1]


def test_exact_route_boundary_uses_route_level_jwt():
    assert AI_WORKFLOW_JWT_PATH.match("/api/v1/ai-workforce/goals")
    assert not AI_WORKFLOW_JWT_PATH.match("/api/v1/ai-workforce-evil/goals")


def test_every_dangerous_autonomy_flag_defaults_off():
    s = Settings()
    s.validate_safety()
    assert s.ai_workflow_engine_enabled and s.ai_workflow_staging_enabled
    assert not any(
        (
            s.ai_workflow_production_autonomy_enabled,
            s.ai_workflow_autonomous_external_delivery_enabled,
            s.ai_workflow_autonomous_financial_actions_enabled,
            s.ai_workflow_autonomous_telephony_enabled,
            s.ai_workflow_autonomous_trading_enabled,
            s.ai_workflow_destructive_actions_enabled,
            s.ai_workflow_unbounded_recursion_enabled,
        )
    )


def test_all_required_durable_tables_are_migrated():
    source = (
        ROOT / "migrations/versions/0030_ai_workflow_control_plane.py"
    ).read_text()
    names = (
        "goals",
        "goal_versions",
        "plans",
        "plan_versions",
        "plan_steps",
        "workflow_definitions",
        "workflow_versions",
        "workflow_instances",
        "workflow_events",
        "workflow_state_transitions",
        "workflow_tasks",
        "workflow_task_dependencies",
        "workflow_schedules",
        "workflow_recurrence_rules",
        "workflow_timers",
        "workflow_conditions",
        "workflow_waits",
        "workflow_approvals",
        "workflow_human_tasks",
        "workflow_retries",
        "workflow_compensations",
        "workflow_escalations",
        "workflow_dead_letters",
        "workflow_reconciliation",
        "workflow_costs",
        "workflow_metrics",
        "workflow_incidents",
        "workflow_audit_events",
    )
    for name in names:
        assert f"ai_{name}" in source
    assert (
        "state_version" in source and "UNIQUE(workflow_public_id,to_version)" in source
    )


def test_api_never_calls_external_providers_directly():
    source = (ROOT / "app/api/v1/ai_workflows.py").read_text().lower()
    for forbidden in (
        "requests.",
        "httpx.",
        "odoo.internal",
        "n8n.internal",
        "postiz",
        "vicidial",
        "live_trading",
    ):
        assert forbidden not in source
