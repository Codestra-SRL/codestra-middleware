"""AI job foundation: durable jobs, events and attempts.

Revision ID: 0032_ai_platform_foundation
Revises: 0031_social_provider_callbacks
"""

from alembic import op

revision = "0032_ai_platform_foundation"
down_revision = "0031_social_provider_callbacks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE ai_job (
      id uuid PRIMARY KEY,
      tenant_id varchar(128) NOT NULL,
      workspace_id varchar(128),
      service_code varchar(64) NOT NULL,
      task_code varchar(96) NOT NULL,
      status varchar(32) NOT NULL,
      priority integer NOT NULL DEFAULT 5,
      requested_by varchar(128),
      prompt_version_id varchar(128),
      model_policy_id varchar(128),
      input_payload jsonb NOT NULL,
      context_payload jsonb,
      output_payload jsonb,
      error_code varchar(64),
      error_message varchar(512),
      idempotency_key varchar(255) NOT NULL,
      request_hash char(64) NOT NULL,
      correlation_id varchar(128) NOT NULL,
      requires_approval boolean NOT NULL DEFAULT false,
      attempt_count integer NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now(),
      started_at timestamptz,
      completed_at timestamptz,
      cancelled_at timestamptz,
      UNIQUE (tenant_id, idempotency_key),
      CHECK (priority BETWEEN 0 AND 9),
      CHECK (attempt_count >= 0)
    )""")
    op.execute("CREATE INDEX ix_ai_job_status_priority ON ai_job(status, priority, created_at)")
    op.execute("CREATE INDEX ix_ai_job_workspace ON ai_job(tenant_id, workspace_id)")
    op.execute("""CREATE TABLE ai_job_event (
      id uuid PRIMARY KEY,
      ai_job_id uuid NOT NULL REFERENCES ai_job(id) ON DELETE RESTRICT,
      event_type varchar(64) NOT NULL,
      event_version integer NOT NULL DEFAULT 1,
      payload jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_ai_job_event_job ON ai_job_event(ai_job_id, created_at)")
    op.execute("""CREATE TABLE ai_job_attempt (
      id uuid PRIMARY KEY,
      ai_job_id uuid NOT NULL REFERENCES ai_job(id) ON DELETE RESTRICT,
      attempt_number integer NOT NULL,
      model_id varchar(128),
      workflow_id varchar(128),
      workflow_execution_id varchar(128),
      status varchar(32) NOT NULL,
      started_at timestamptz NOT NULL,
      completed_at timestamptz,
      duration_ms integer,
      error_class varchar(64),
      error_code varchar(64),
      error_message varchar(512),
      UNIQUE (ai_job_id, attempt_number)
    )""")


def downgrade() -> None:
    op.drop_table("ai_job_attempt")
    op.drop_table("ai_job_event")
    op.drop_index("ix_ai_job_workspace", table_name="ai_job")
    op.drop_index("ix_ai_job_status_priority", table_name="ai_job")
    op.drop_table("ai_job")
