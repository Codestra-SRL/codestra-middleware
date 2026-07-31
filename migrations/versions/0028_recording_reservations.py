"""Durable recording reservation state."""

from alembic import op
import sqlalchemy as sa

revision = "0028_recording_reservations"
down_revision = "0027_telephony_command_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recording_reservation",
        sa.Column("recording_uid", sa.String(64), primary_key=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("campaign_id", sa.String(64), nullable=False),
        sa.Column("opaque_object_id", sa.String(128), nullable=False),
        sa.Column("vicidial_recording_id", sa.String(64), nullable=False),
        sa.Column("vicidial_call_id", sa.String(128), nullable=False),
        sa.Column("asterisk_uniqueid", sa.String(128), nullable=False),
        sa.Column("expected_sha256", sa.String(64), nullable=False),
        sa.Column("expected_size", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("codec", sa.String(32), nullable=False),
        sa.Column("channels", sa.Integer(), nullable=False),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("object_version", sa.String(255)),
        sa.Column("odoo_reference", sa.String(128)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "environment", "idempotency_key",
            name="uq_recording_reservation_environment_key",
        ),
        sa.UniqueConstraint(
            "object_version", name="uq_recording_reservation_object_version",
        ),
        sa.CheckConstraint(
            "environment IN ('staging','production')",
            name="ck_recording_reservation_environment",
        ),
    )


def downgrade() -> None:
    op.drop_table("recording_reservation")
