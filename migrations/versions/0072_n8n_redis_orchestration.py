"""Workflow orchestration, worker presence, and durable dead-letter metadata."""
from alembic import op

revision = "0072_n8n_redis_orchestration"
down_revision = "0071_telephony_sections_6_10_11_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE workflow_definition_control (
      id uuid PRIMARY KEY, workflow_code varchar(128) NOT NULL UNIQUE, workflow_version varchar(64) NOT NULL,
      owner varchar(128) NOT NULL, state varchar(32) NOT NULL DEFAULT 'DRAFT', required_capabilities jsonb NOT NULL DEFAULT '[]'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE workflow_execution_control (
      id uuid PRIMARY KEY, workflow_code varchar(128) NOT NULL, workflow_version varchar(64) NOT NULL, tenant_id varchar(128) NOT NULL,
      workspace_id varchar(128) NOT NULL, command_id varchar(128) NOT NULL, idempotency_key varchar(255) NOT NULL UNIQUE, state varchar(32) NOT NULL DEFAULT 'OUTBOX_PENDING', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE workflow_dead_letter_control (
      id uuid PRIMARY KEY, execution_id uuid NOT NULL, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      failure_class varchar(48) NOT NULL, attempt_count integer NOT NULL DEFAULT 0, review_status varchar(24) NOT NULL DEFAULT 'OPEN', replay_allowed boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE workflow_worker_presence (
      id uuid PRIMARY KEY, worker_id varchar(128) NOT NULL UNIQUE, worker_group varchar(64) NOT NULL, state varchar(24) NOT NULL DEFAULT 'STARTING',
      active_execution_count integer NOT NULL DEFAULT 0, version varchar(64) NOT NULL DEFAULT 'unknown', last_heartbeat_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE workflow_circuit_breaker_control (
      id uuid PRIMARY KEY, provider varchar(96) NOT NULL UNIQUE, state varchar(24) NOT NULL DEFAULT 'CLOSED', consecutive_failures integer NOT NULL DEFAULT 0,
      opened_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for table in ("workflow_execution_control", "workflow_dead_letter_control"):
        op.execute(f"CREATE INDEX ix_{table}_scope ON {table}(tenant_id,workspace_id,state)")


def downgrade() -> None:
    for table in ("workflow_circuit_breaker_control", "workflow_worker_presence", "workflow_dead_letter_control", "workflow_execution_control", "workflow_definition_control"):
        op.drop_table(table)
