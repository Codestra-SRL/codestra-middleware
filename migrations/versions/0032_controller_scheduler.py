"""Add durable restricted-controller scheduler state.

Revision ID: 0032_controller_scheduler
Revises: 0031_ai_orchestration_v1
"""

from alembic import op

revision = "0032_controller_scheduler"
down_revision = "0031_ai_orchestration_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        """CREATE TABLE controller_tasks (
          id uuid PRIMARY KEY, tenant_id text NOT NULL, workspace text NOT NULL,
          title text NOT NULL, objective text NOT NULL, request_id text NOT NULL,
          correlation_id text NOT NULL, idempotency_key_hash char(64) NOT NULL,
          request_hash char(64) NOT NULL, plan jsonb NOT NULL DEFAULT '[]'::jsonb,
          plan_hash char(64), state text NOT NULL DEFAULT 'CREATED',
          priority smallint NOT NULL DEFAULT 5, timeout_seconds integer NOT NULL DEFAULT 600,
          max_attempts integer NOT NULL DEFAULT 3, attempt_count integer NOT NULL DEFAULT 0,
          available_at timestamptz, lease_owner text, lease_expires_at timestamptz,
          heartbeat_at timestamptz, last_error_code text, version bigint NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE(tenant_id,idempotency_key_hash),
          CONSTRAINT ck_controller_task_state CHECK (state IN
          ('CREATED','PLANNING','PLAN_READY','AWAITING_APPROVAL','APPROVED','QUEUED',
           'RUNNING','EXECUTING','VERIFYING','COMPLETED','FAILED','CANCELLED',
           'DEAD_LETTER','SUSPENDED')),
          CONSTRAINT ck_controller_priority CHECK(priority BETWEEN 0 AND 9),
          CONSTRAINT ck_controller_attempts CHECK(max_attempts BETWEEN 1 AND 10)
        )""",
        """CREATE INDEX ix_controller_tasks_claim
        ON controller_tasks(state,priority DESC,available_at,created_at)""",
        """CREATE INDEX ix_controller_tasks_tenant
        ON controller_tasks(tenant_id,state,updated_at DESC)""",
        """CREATE TABLE controller_approvals (
          id uuid PRIMARY KEY, task_id uuid NOT NULL REFERENCES controller_tasks(id) ON DELETE RESTRICT,
          tenant_id text NOT NULL, plan_hash char(64) NOT NULL, server_id text NOT NULL,
          tools jsonb NOT NULL, approver_fingerprint char(64) NOT NULL,
          token_jti_hash char(64) NOT NULL UNIQUE, token_expires_at timestamptz NOT NULL,
          consumed_at timestamptz, state text NOT NULL DEFAULT 'APPROVED',
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT ck_controller_approval_state CHECK(state IN ('APPROVED','REJECTED','EXPIRED','CONSUMED'))
        )""",
        """CREATE TABLE controller_task_audit (
          id bigserial PRIMARY KEY, task_id uuid NOT NULL REFERENCES controller_tasks(id) ON DELETE RESTRICT,
          tenant_id text NOT NULL, sequence bigint NOT NULL, action text NOT NULL,
          safe_details jsonb NOT NULL DEFAULT '{}'::jsonb, previous_hash char(64) NOT NULL,
          record_hash char(64) NOT NULL, correlation_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(task_id,sequence)
        )""",
        """CREATE TABLE controller_verifications (
          verification_code text PRIMARY KEY, task_id uuid NOT NULL REFERENCES controller_tasks(id) ON DELETE RESTRICT,
          execution_id uuid NOT NULL, tenant_id text NOT NULL, checks jsonb NOT NULL,
          evidence_hash char(64) NOT NULL, signature text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )""",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    for statement in (
        "DROP TABLE controller_verifications",
        "DROP TABLE controller_task_audit",
        "DROP TABLE controller_approvals",
        "DROP INDEX ix_controller_tasks_tenant",
        "DROP INDEX ix_controller_tasks_claim",
        "DROP TABLE controller_tasks",
    ):
        op.execute(statement)
