"""Add durable dynamic identity and lead reservations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0028_dynamic_allocation_reservations"
down_revision = "0027_extension_pool_exclusions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_allocation_reservation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_public_id", sa.String(128), nullable=False),
        sa.Column("environment", sa.String(24), nullable=False),
        sa.Column("organization_public_id", sa.String(128), nullable=False),
        sa.Column("business_unit_public_id", sa.String(128), nullable=False),
        sa.Column("campaign_public_id", sa.String(128)),
        sa.Column("purpose", sa.String(128), nullable=False),
        sa.Column("idempotency_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("provider_checks", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="RESERVED"),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True)),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "resource_type IN ('AGENT_PUBLIC_ID','LEAD_PUBLIC_ID','PHONE_PUBLIC_ID','ENDPOINT_PUBLIC_ID','INTERNAL_TEST_DESTINATION')",
            name="ck_allocation_resource_type",
        ),
        sa.CheckConstraint(
            "state IN ('RESERVED','COMMITTED','RELEASED','EXPIRED','COMPENSATION_REQUIRED')",
            name="ck_allocation_state",
        ),
    )
    op.create_index(
        "uq_allocation_active_resource",
        "integration_allocation_reservation",
        ["resource_type", "resource_public_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('RESERVED','COMMITTED')"),
    )


def downgrade() -> None:
    op.drop_index("uq_allocation_active_resource", table_name="integration_allocation_reservation")
    op.drop_table("integration_allocation_reservation")
