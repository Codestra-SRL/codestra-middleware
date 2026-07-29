"""Store extension exclusions as allocation-pool data."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0027_extension_pool_exclusions"
down_revision = "0026_generic_event_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "telephony_extension_pool",
        sa.Column("excluded_extensions", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_check_constraint(
        "ck_telephony_reserved_extensions",
        "telephony_extension_reservation",
        "extension NOT IN (6000, 6110, 6197, 6198)",
    )
    op.execute(
        "UPDATE telephony_extension_pool "
        "SET excluded_extensions = '[6000,6110,6197,6198]'::jsonb "
        "WHERE excluded_extensions = '[]'::jsonb"
    )


def downgrade() -> None:
    op.drop_constraint("ck_telephony_reserved_extensions", "telephony_extension_reservation", type_="check")
    op.drop_column("telephony_extension_pool", "excluded_extensions")
