"""Add telephony command and operation journals.

Revision ID: 0027_telephony_command_journal
Revises: 0026_n8n_contracts
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_telephony_command_journal"
down_revision = "0026_n8n_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "telephony_command_journal",
        sa.Column("command_id", uuid, nullable=False),
        sa.Column("command_type", sa.String(96), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_public_id", sa.String(144), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("business_unit_public_id", sa.String(144), nullable=False),
        sa.Column("campaign_public_id", sa.String(144), nullable=False),
        sa.Column("idempotency_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("causation_id", sa.String(128), nullable=False),
        sa.Column("policy_decision_id", sa.String(144), nullable=False),
        sa.Column("policy_decision_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", jsonb, nullable=False),
        sa.Column("request_json", jsonb, nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column(
            "attempt_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("aggregate_version >= 1", name="ck_telephony_command_version"),
        sa.CheckConstraint(
            "environment IN ('staging','test','production')",
            name="ck_telephony_command_environment",
        ),
        sa.PrimaryKeyConstraint("command_id"),
        sa.UniqueConstraint("idempotency_hash"),
    )
    op.create_index(
        "ix_telephony_command_aggregate",
        "telephony_command_journal",
        ["aggregate_type", "aggregate_public_id", "aggregate_version"],
    )
    op.create_index(
        "ix_telephony_command_correlation",
        "telephony_command_journal",
        ["correlation_id"],
    )
    op.create_table(
        "telephony_operation_journal",
        sa.Column("operation_id", uuid, nullable=False),
        sa.Column("command_id", uuid, nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("endpoint_key", sa.String(96), nullable=False),
        sa.Column("readback_endpoint_key", sa.String(96), nullable=False),
        sa.Column("target_configuration_checksum", sa.String(71), nullable=False),
        sa.Column("target_attested", sa.Boolean(), nullable=False),
        sa.Column("desired_hash", sa.String(64), nullable=False),
        sa.Column("actual_hash", sa.String(64), nullable=True),
        sa.Column("readback_matches", sa.Boolean(), nullable=True),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("response_json", jsonb, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(readback_matches IS NOT TRUE) OR (actual_hash IS NOT NULL)",
            name="ck_telephony_operation_readback_hash",
        ),
        sa.ForeignKeyConstraint(
            ["command_id"],
            ["telephony_command_journal.command_id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint("command_id"),
    )
    op.create_index(
        "ix_telephony_operation_correlation",
        "telephony_operation_journal",
        ["correlation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telephony_operation_correlation",
        table_name="telephony_operation_journal",
    )
    op.drop_table("telephony_operation_journal")
    op.drop_index(
        "ix_telephony_command_correlation", table_name="telephony_command_journal"
    )
    op.drop_index(
        "ix_telephony_command_aggregate", table_name="telephony_command_journal"
    )
    op.drop_table("telephony_command_journal")
