"""Merge current lifecycle heads and add durable delivery receipts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0030_outbox_delivery_receipts"
down_revision = ("0029_n8n_results", "0027_telephony_command_journal")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_delivery_receipt",
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "outbox_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outbox_event.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_key", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_json", postgresql.JSONB()),
        sa.Column("response_hash", sa.String(64)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "outbox_event_id",
            "target_key",
            name="uq_outbox_receipt_event_target",
        ),
        sa.UniqueConstraint(
            "target_key",
            "idempotency_key",
            name="uq_outbox_receipt_target_idempotency",
        ),
    )


def downgrade() -> None:
    op.drop_table("outbox_delivery_receipt")
