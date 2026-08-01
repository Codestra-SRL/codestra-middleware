"""Link ingress and transport rows to the canonical integration event.

Revision ID: 0021_canonical_event_lifecycle
Revises: 0020_outbox_delivery_receipts
"""
from alembic import op
import sqlalchemy as sa


revision = "0021_canonical_event_lifecycle"
down_revision = "0020_outbox_delivery_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "integration_event",
        sa.Column("environment", sa.String(24), nullable=True),
    )
    op.add_column(
        "integration_event",
        sa.Column("originating_odoo_outbox_id", sa.String(128), nullable=True),
    )
    op.execute("UPDATE integration_event SET environment = 'staging' WHERE environment IS NULL")
    op.execute(
        "UPDATE integration_event SET originating_odoo_outbox_id = original_event_id "
        "WHERE source_system = 'odoo' AND originating_odoo_outbox_id IS NULL"
    )
    op.alter_column("integration_event", "environment", nullable=False)
    op.create_check_constraint(
        "ck_integration_event_odoo_outbox_binding",
        "integration_event",
        "source_system <> 'odoo' OR originating_odoo_outbox_id IS NOT NULL",
    )
    op.create_unique_constraint(
        "uq_integration_event_source_environment_idempotency",
        "integration_event",
        ["source_system", "environment", "idempotency_key"],
    )
    op.create_unique_constraint(
        "uq_integration_event_originating_odoo_outbox",
        "integration_event",
        ["source_system", "originating_odoo_outbox_id"],
    )

    op.add_column(
        "event_inbox",
        sa.Column("integration_event_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        "UPDATE event_inbox inbox SET integration_event_id = event.id "
        "FROM integration_event event WHERE event.original_event_id = inbox.event_id"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM event_inbox "
        "WHERE source = 'odoo' AND integration_event_id IS NULL) "
        "THEN RAISE EXCEPTION 'Odoo inbox rows cannot be mapped to integration_event'; "
        "END IF; END $$"
    )
    op.create_foreign_key(
        "fk_event_inbox_integration_event",
        "event_inbox", "integration_event", ["integration_event_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_event_inbox_integration_event", "event_inbox", ["integration_event_id"]
    )
    op.create_check_constraint(
        "ck_event_inbox_odoo_event_binding",
        "event_inbox",
        "source <> 'odoo' OR integration_event_id IS NOT NULL",
    )

    op.add_column(
        "outbox_event",
        sa.Column("integration_event_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        "UPDATE outbox_event outbox SET integration_event_id = event.id "
        "FROM integration_event event "
        "WHERE COALESCE(outbox.payload->>'event_id', outbox.payload->'payload'->>'event_id') "
        "= event.original_event_id"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM outbox_event "
        "WHERE topic = 'event.accepted' AND integration_event_id IS NULL) "
        "THEN RAISE EXCEPTION 'accepted event outbox rows cannot be mapped to integration_event'; "
        "END IF; END $$"
    )
    op.create_foreign_key(
        "fk_outbox_event_integration_event",
        "outbox_event", "integration_event", ["integration_event_id"], ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_outbox_event_integration_event_id", "outbox_event", ["integration_event_id"]
    )
    op.create_check_constraint(
        "ck_outbox_event_accepted_event_binding",
        "outbox_event",
        "topic <> 'event.accepted' OR integration_event_id IS NOT NULL",
    )

    op.drop_constraint("ck_n8n_execution_status", "n8n_execution", type_="check")
    op.create_check_constraint(
        "ck_n8n_execution_status", "n8n_execution",
        "status IN ('REGISTERED','RUNNING','SUCCEEDED','FAILED','CANCELLED','DEAD_LETTERED')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_n8n_execution_status", "n8n_execution", type_="check")
    op.execute(
        "UPDATE n8n_execution SET status = 'FAILED' WHERE status = 'DEAD_LETTERED'"
    )
    op.create_check_constraint(
        "ck_n8n_execution_status", "n8n_execution",
        "status IN ('REGISTERED','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
    )
    op.drop_constraint(
        "ck_outbox_event_accepted_event_binding", "outbox_event", type_="check"
    )
    op.drop_index("ix_outbox_event_integration_event_id", table_name="outbox_event")
    op.drop_constraint("fk_outbox_event_integration_event", "outbox_event", type_="foreignkey")
    op.drop_column("outbox_event", "integration_event_id")
    op.drop_constraint(
        "ck_event_inbox_odoo_event_binding", "event_inbox", type_="check"
    )
    op.drop_constraint("uq_event_inbox_integration_event", "event_inbox", type_="unique")
    op.drop_constraint("fk_event_inbox_integration_event", "event_inbox", type_="foreignkey")
    op.drop_column("event_inbox", "integration_event_id")
    op.drop_constraint(
        "uq_integration_event_originating_odoo_outbox", "integration_event", type_="unique"
    )
    op.drop_constraint(
        "ck_integration_event_odoo_outbox_binding", "integration_event", type_="check"
    )
    op.drop_constraint(
        "uq_integration_event_source_environment_idempotency",
        "integration_event", type_="unique",
    )
    op.drop_column("integration_event", "originating_odoo_outbox_id")
    op.drop_column("integration_event", "environment")
