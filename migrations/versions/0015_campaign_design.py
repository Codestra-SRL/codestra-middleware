"""Persistent automatic campaign design and Odoo event receipts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_campaign_design"
down_revision = "0014_telephony_call_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "campaign_design_revision",
        sa.Column("integration_uuid", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("manifest", postgresql.JSONB, nullable=False),
        sa.Column("approval_state", sa.String(24), nullable=False),
        sa.Column("approved_by", sa.String(128)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("integration_uuid", "revision"),
        sa.UniqueConstraint("integration_uuid", "payload_hash",
                            name="uq_campaign_design_payload"),
        sa.CheckConstraint("revision >= 1", name="ck_campaign_design_revision"),
        sa.CheckConstraint("approval_state IN ('preview','approved')",
                           name="ck_campaign_design_approval"),
    )
    op.create_table(
        "campaign_list_reservation",
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("business_unit", sa.String(16), nullable=False),
        sa.Column("list_id", sa.Integer, nullable=False),
        sa.Column("integration_uuid", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.UniqueConstraint("environment", "list_id",
                            name="uq_campaign_list_environment_id"),
        sa.UniqueConstraint("environment", "integration_uuid", "revision",
                            name="uq_campaign_list_revision"),
    )
    op.create_table(
        "campaign_design_event",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("integration_uuid", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(128)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('retry','completed','dead_letter')",
                           name="ck_campaign_design_event_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_campaign_design_event_attempts"),
    )


def downgrade():
    op.drop_table("campaign_design_event")
    op.drop_table("campaign_list_reservation")
    op.drop_table("campaign_design_revision")
