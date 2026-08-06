"""Add durable worker dead-letter evidence and recovery controls.

Revision ID: 0032_ai_worker_queue_runtime
Revises: 0031_ai_orchestration_v1
"""

from alembic import op

revision = "0032_ai_worker_queue_runtime"
down_revision = "0031_ai_orchestration_v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        "CREATE EXTENSION IF NOT EXISTS pgcrypto",
        """ALTER TABLE ai_job_dead_letters
        ADD COLUMN final_error_code text,
        ADD COLUMN max_attempts integer,
        ADD COLUMN safe_error_details jsonb NOT NULL DEFAULT '{}'::jsonb,
        ADD COLUMN failed_at timestamptz,
        ADD COLUMN task_id uuid,
        ADD COLUMN tenant_id uuid,
        ADD COLUMN correlation_id text,
        ADD COLUMN evidence_hash char(64),
        ADD COLUMN manual_retry_requires_new_approval boolean NOT NULL DEFAULT true""",
        """UPDATE ai_job_dead_letters d SET
        final_error_code=d.safe_error_code,
        max_attempts=LEAST(j.max_attempts,d.attempt_count),
        failed_at=d.created_at,
        task_id=d.job_id,
        tenant_id=d.organization_id,
        correlation_id=COALESCE(j.correlation_id,'legacy-dead-letter'),
        evidence_hash=encode(digest(d.job_id::text || ':' || d.safe_error_code || ':' ||
          d.attempt_count::text,'sha256'),'hex')
        FROM ai_generation_jobs j WHERE j.id=d.job_id""",
        "ALTER TABLE ai_job_dead_letters ALTER COLUMN final_error_code SET NOT NULL",
        "ALTER TABLE ai_job_dead_letters ALTER COLUMN max_attempts SET NOT NULL",
        "ALTER TABLE ai_job_dead_letters ALTER COLUMN failed_at SET NOT NULL",
        "ALTER TABLE ai_job_dead_letters ALTER COLUMN task_id SET NOT NULL",
        "ALTER TABLE ai_job_dead_letters ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE ai_job_dead_letters ALTER COLUMN correlation_id SET NOT NULL",
        "ALTER TABLE ai_job_dead_letters ALTER COLUMN evidence_hash SET NOT NULL",
        "ALTER TABLE ai_job_dead_letters ADD CONSTRAINT ck_ai_dead_letter_attempts CHECK (attempt_count > 0 AND max_attempts > 0)",
        "ALTER TABLE ai_job_dead_letters ADD CONSTRAINT ck_ai_dead_letter_evidence CHECK (evidence_hash ~ '^[0-9a-f]{64}$')",
        "CREATE INDEX ix_ai_dead_letter_tenant_failed ON ai_job_dead_letters(tenant_id,workspace_id,failed_at DESC)",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    for statement in (
        "DROP INDEX ix_ai_dead_letter_tenant_failed",
        "ALTER TABLE ai_job_dead_letters DROP CONSTRAINT ck_ai_dead_letter_evidence",
        "ALTER TABLE ai_job_dead_letters DROP CONSTRAINT ck_ai_dead_letter_attempts",
        """ALTER TABLE ai_job_dead_letters
        DROP COLUMN manual_retry_requires_new_approval,
        DROP COLUMN evidence_hash,
        DROP COLUMN correlation_id,
        DROP COLUMN tenant_id,
        DROP COLUMN task_id,
        DROP COLUMN failed_at,
        DROP COLUMN safe_error_details,
        DROP COLUMN max_attempts,
        DROP COLUMN final_error_code""",
    ):
        op.execute(statement)
