"""Durable AI Workforce workflow control plane."""

from alembic import op

revision = "0030_ai_workflow_control_plane"
down_revision = "0029_merge_lead_recording_heads"
branch_labels = None
depends_on = None

STATEMENTS = [
    """CREATE TABLE ai_goals (public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, external_key varchar(128) NOT NULL, goal_type varchar(32) NOT NULL, status varchar(32) NOT NULL, desired_outcome text NOT NULL, business_owner varchar(128) NOT NULL, ai_employee_owner varchar(128) NOT NULL, deadline timestamptz NOT NULL, priority varchar(16) NOT NULL, policy_json jsonb NOT NULL, created_by varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,workspace_id,external_key))""",
    """CREATE TABLE ai_plans (public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, goal_public_id varchar(64) NOT NULL REFERENCES ai_goals(public_id), status varchar(32) NOT NULL, version integer NOT NULL DEFAULT 1, plan_json jsonb NOT NULL, plan_hash char(64) NOT NULL, created_by varchar(128) NOT NULL, reviewed_by varchar(128), reviewed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(goal_public_id,version))""",
    """CREATE TABLE ai_workflow_instances (public_id varchar(64) PRIMARY KEY, workflow_definition_id varchar(64) NOT NULL, workflow_version integer NOT NULL, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, goal_public_id varchar(64) NOT NULL REFERENCES ai_goals(public_id), initiated_by varchar(128) NOT NULL, assigned_employee_id varchar(128) NOT NULL, manager_employee_id varchar(128) NOT NULL, status varchar(32) NOT NULL, priority varchar(16) NOT NULL, risk_level varchar(16) NOT NULL, budget_limit numeric(18,4) NOT NULL, token_limit bigint NOT NULL, tool_limit integer NOT NULL, task_limit integer NOT NULL CHECK(task_limit BETWEEN 1 AND 250), started_at timestamptz, due_at timestamptz NOT NULL, completed_at timestamptz, cancelled_at timestamptz, current_step varchar(128) NOT NULL, state_version bigint NOT NULL CHECK(state_version>0), trace_id varchar(64) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE INDEX ix_ai_workflow_scope_status ON ai_workflow_instances(tenant_id,workspace_id,status,due_at)""",
    """CREATE TABLE ai_workflow_state_transitions (id bigserial PRIMARY KEY, workflow_public_id varchar(64) NOT NULL REFERENCES ai_workflow_instances(public_id), tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, from_status varchar(32) NOT NULL, to_status varchar(32) NOT NULL, from_version bigint NOT NULL, to_version bigint NOT NULL, actor_subject varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(workflow_public_id,to_version), CHECK(to_version=from_version+1))""",
    """CREATE TABLE ai_workflow_idempotency (tenant_id varchar(128) NOT NULL, operation varchar(64) NOT NULL, idempotency_key varchar(255) NOT NULL, request_hash char(64) NOT NULL, response_json jsonb NOT NULL, expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(tenant_id,operation,idempotency_key))""",
]

GENERIC_TABLES = (
    "ai_goal_versions",
    "ai_plan_versions",
    "ai_plan_steps",
    "ai_workflow_definitions",
    "ai_workflow_versions",
    "ai_workflow_events",
    "ai_workflow_tasks",
    "ai_workflow_task_dependencies",
    "ai_workflow_schedules",
    "ai_workflow_recurrence_rules",
    "ai_workflow_timers",
    "ai_workflow_conditions",
    "ai_workflow_waits",
    "ai_workflow_approvals",
    "ai_workflow_human_tasks",
    "ai_workflow_retries",
    "ai_workflow_compensations",
    "ai_workflow_escalations",
    "ai_workflow_dead_letters",
    "ai_workflow_reconciliation",
    "ai_workflow_costs",
    "ai_workflow_metrics",
    "ai_workflow_incidents",
    "ai_workflow_audit_events",
)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    for table in GENERIC_TABLES:
        op.execute(
            f"""CREATE TABLE {table} (public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, workflow_public_id varchar(64), state varchar(32) NOT NULL DEFAULT 'DRAFT', state_version bigint NOT NULL DEFAULT 1, external_key varchar(128) NOT NULL, payload_json jsonb NOT NULL DEFAULT '{{}}', available_at timestamptz, lease_owner varchar(128), lease_expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,workspace_id,external_key))"""
        )
    op.execute(
        "CREATE UNIQUE INDEX uq_ai_workflow_event_dedup ON ai_workflow_events(tenant_id,external_key)"
    )


def downgrade() -> None:
    for table in reversed(GENERIC_TABLES):
        op.execute(f"DROP TABLE {table}")
    for table in (
        "ai_workflow_idempotency",
        "ai_workflow_state_transitions",
        "ai_workflow_instances",
        "ai_plans",
        "ai_goals",
    ):
        op.execute(f"DROP TABLE {table}")
