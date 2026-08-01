"""Persist external delivery receipts on the durable outbox."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0020_outbox_delivery_receipts"
down_revision = "0019_execution_trace_allocator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outbox_event", sa.Column("response_json", postgresql.JSONB()))
    op.add_column("outbox_event", sa.Column("acknowledged_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("outbox_event", "acknowledged_at")
    op.drop_column("outbox_event", "response_json")
