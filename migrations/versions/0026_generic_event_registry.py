"""Add the generic event schema-registry binding table."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_generic_event_registry"
down_revision = "0025_endpoint_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_event_type",
        sa.Column("event_type_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("producer_service", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("kill_switch", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_type", "schema_version", "producer_service", name="uq_integration_event_binding"),
    )


def downgrade() -> None:
    op.drop_table("integration_event_type")

