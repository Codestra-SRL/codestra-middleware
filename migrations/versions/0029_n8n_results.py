"""Persist n8n results before terminal acknowledgements."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_n8n_results"
down_revision = "0028_dynamic_allocation_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "n8n_result",
        sa.Column("result_id", sa.String(128), primary_key=True),
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("delivery_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("execution_id", sa.String(128), nullable=False),
        sa.Column("workflow_id", sa.String(128), nullable=False),
        sa.Column("workflow_version", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("result_classification", sa.String(64), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("policy_hash", sa.String(64), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["registration_id"], ["n8n_execution_registration.registration_id"]),
        sa.ForeignKeyConstraint(["delivery_id"], ["broad_event_delivery.delivery_id"]),
        sa.UniqueConstraint("registration_id", name="uq_n8n_result_registration"),
    )
    op.add_column("n8n_acknowledgement", sa.Column("result_id", sa.String(128)))
    op.create_foreign_key("fk_n8n_ack_result", "n8n_acknowledgement", "n8n_result", ["result_id"], ["result_id"])


def downgrade() -> None:
    op.drop_constraint("fk_n8n_ack_result", "n8n_acknowledgement", type_="foreignkey")
    op.drop_column("n8n_acknowledgement", "result_id")
    op.drop_table("n8n_result")
