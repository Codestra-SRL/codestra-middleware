"""Add immutable tenant-scoped enterprise event store.

Revision ID: 0031_enterprise_event_store
Revises: 0030_enterprise_identity_core
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0031_enterprise_event_store"
down_revision = "0030_enterprise_identity_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enterprise_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(96), nullable=False),
        sa.Column("aggregate_id", sa.String(128), nullable=False),
        sa.Column("aggregate_sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("causation_id", sa.String(128)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("recorded_by", sa.String(128), nullable=False),
        sa.UniqueConstraint("tenant_id", "workspace_id", "event_id", name="uq_enterprise_event_scope_id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "aggregate_type", "aggregate_id", "aggregate_sequence",
            name="uq_enterprise_event_aggregate_sequence",
        ),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "idempotency_key_hash",
            name="uq_enterprise_event_idempotency",
        ),
        sa.CheckConstraint("aggregate_sequence >= 1", name="ck_enterprise_event_sequence"),
    )
    op.create_index(
        "ix_enterprise_event_scope_time", "enterprise_event",
        ["tenant_id", "workspace_id", "recorded_at"],
    )
    op.create_table(
        "enterprise_event_replay",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(512), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["enterprise_event.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("event_id", "requested_by", "reason", name="uq_enterprise_event_replay_request"),
        sa.CheckConstraint("status IN ('PENDING','RUNNING','COMPLETED','FAILED','DEAD_LETTER')", name="ck_enterprise_event_replay_status"),
        sa.CheckConstraint("attempts BETWEEN 0 AND 5", name="ck_enterprise_event_replay_attempts"),
    )

    op.execute("""
        CREATE OR REPLACE FUNCTION reject_enterprise_event_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'enterprise events are immutable';
        END $$
    """)
    op.execute("""
        CREATE TRIGGER enterprise_event_immutable
        BEFORE UPDATE OR DELETE ON enterprise_event
        FOR EACH ROW EXECUTE FUNCTION reject_enterprise_event_mutation()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS enterprise_event_immutable ON enterprise_event")
    op.execute("DROP FUNCTION IF EXISTS reject_enterprise_event_mutation()")
    op.drop_table("enterprise_event_replay")
    op.drop_index("ix_enterprise_event_scope_time", table_name="enterprise_event")
    op.drop_table("enterprise_event")
