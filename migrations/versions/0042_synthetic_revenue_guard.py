"""Keep synthetic canary revenue outside ordinary reporting.

Revision ID: 0042_synthetic_revenue_guard
Revises: 0041_lead_identity_revenue
"""

from alembic import op

revision = "0042_synthetic_revenue_guard"
down_revision = "0041_lead_identity_revenue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE revenue_events ADD COLUMN is_synthetic boolean NOT NULL DEFAULT false"
    )
    op.execute(
        "CREATE INDEX ix_revenue_events_reporting ON revenue_events(tenant_id,occurred_at) WHERE is_synthetic=false"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_revenue_events_reporting")
    op.execute("ALTER TABLE revenue_events DROP COLUMN is_synthetic")
