"""Add IAM governance and durable event delivery state.

Revision ID: 0032_enterprise_core_completion
Revises: 0031_enterprise_event_store
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0032_enterprise_core_completion"
down_revision = "0031_enterprise_event_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "iam_api_key",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_id", sa.String(96), nullable=False),
        sa.Column("secret_hash", sa.String(128), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String(96)), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["principal_id"], ["iam_principal.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "workspace_id", "key_id", name="uq_iam_api_key_scope"),
        sa.CheckConstraint("version >= 1", name="ck_iam_api_key_version"),
    )
    op.create_table(
        "iam_access_review",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("status IN ('OPEN','IN_PROGRESS','COMPLETED','EXPIRED','CANCELLED')", name="ck_iam_access_review_status"),
    )
    op.create_table(
        "iam_access_review_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("review_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(24)),
        sa.Column("decided_by", sa.String(128)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("reason", sa.String(512)),
        sa.ForeignKeyConstraint(["review_id"], ["iam_access_review.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["principal_id"], ["iam_principal.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["role_binding_id"], ["iam_role_binding.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("review_id", "role_binding_id", name="uq_iam_review_binding"),
        sa.CheckConstraint("decision IS NULL OR decision IN ('APPROVE','REVOKE','ESCALATE')", name="ck_iam_review_decision"),
    )
    op.create_table(
        "enterprise_event_subscription",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscriber_key", sa.String(96), nullable=False),
        sa.Column("event_type_pattern", sa.String(128), nullable=False),
        sa.Column("endpoint_key", sa.String(96), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.UniqueConstraint("tenant_id", "workspace_id", "subscriber_key", "event_type_pattern", name="uq_event_subscription_scope"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 10", name="ck_event_subscription_attempts"),
    )
    op.create_table(
        "enterprise_event_delivery",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_owner", sa.String(96)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["enterprise_event.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subscription_id"], ["enterprise_event_subscription.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("event_id", "subscription_id", name="uq_event_delivery_once"),
        sa.CheckConstraint("status IN ('PENDING','LEASED','DELIVERED','RETRY','DEAD_LETTER','CANCELLED')", name="ck_event_delivery_status"),
        sa.CheckConstraint("attempts BETWEEN 0 AND 10", name="ck_event_delivery_attempts"),
    )
    op.create_index("ix_event_delivery_claim", "enterprise_event_delivery", ["status", "next_attempt_at", "lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_event_delivery_claim", table_name="enterprise_event_delivery")
    op.drop_table("enterprise_event_delivery")
    op.drop_table("enterprise_event_subscription")
    op.drop_table("iam_access_review_item")
    op.drop_table("iam_access_review")
    op.drop_table("iam_api_key")
