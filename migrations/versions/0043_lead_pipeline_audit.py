"""Add immutable hash-chained lead pipeline audit events.

Revision ID: 0043_lead_pipeline_audit
Revises: 0042_synthetic_revenue_guard
"""

from alembic import op

revision = "0043_lead_pipeline_audit"
down_revision = "0042_synthetic_revenue_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE lead_pipeline_audit_events (
        id uuid PRIMARY KEY,
        tenant_id uuid NOT NULL,
        sequence bigint NOT NULL,
        event_type varchar(64) NOT NULL,
        entity_type varchar(32) NOT NULL,
        entity_id uuid,
        correlation_id varchar(255) NOT NULL,
        actor varchar(128) NOT NULL,
        outcome varchar(32) NOT NULL,
        safe_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
        previous_hash char(64),
        event_hash char(64) NOT NULL,
        occurred_at timestamptz NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(tenant_id, sequence),
        UNIQUE(tenant_id, event_hash),
        CHECK (sequence > 0),
        CHECK (event_hash ~ '^[0-9a-f]{64}$'),
        CHECK (previous_hash IS NULL OR previous_hash ~ '^[0-9a-f]{64}$')
        )"""
    )
    op.execute(
        "CREATE INDEX ix_lead_pipeline_audit_trace ON lead_pipeline_audit_events(tenant_id,correlation_id,sequence)"
    )
    op.execute(
        """CREATE FUNCTION deny_lead_pipeline_audit_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'lead pipeline audit events are immutable';
        END $$"""
    )
    op.execute(
        """CREATE TRIGGER lead_pipeline_audit_no_update
        BEFORE UPDATE ON lead_pipeline_audit_events FOR EACH ROW
        EXECUTE FUNCTION deny_lead_pipeline_audit_mutation()"""
    )
    op.execute(
        """CREATE TRIGGER lead_pipeline_audit_no_delete
        BEFORE DELETE ON lead_pipeline_audit_events FOR EACH ROW
        EXECUTE FUNCTION deny_lead_pipeline_audit_mutation()"""
    )


def downgrade() -> None:
    op.execute("DROP TABLE lead_pipeline_audit_events")
    op.execute("DROP FUNCTION deny_lead_pipeline_audit_mutation")
