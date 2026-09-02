"""Durable agent interaction results (disposition/notes/callback).

Revision ID: 0057_interaction_result
Revises: 0056_klyrow_delivery_events
"""

from alembic import op

revision = "0057_interaction_result"
down_revision = "0056_klyrow_delivery_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE interaction_result (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      interaction_public_id text NOT NULL,
      result_type text NOT NULL CHECK (result_type IN ('notes','disposition','callback')),
      agent_subject text NOT NULL,
      agent_employee_id text NOT NULL,
      crm_lead_public_id text NOT NULL,
      disposition_code text,
      notes_text text,
      callback_scheduled_for timestamptz,
      callback_timezone text,
      callback_reason text,
      correlation_id text NOT NULL,
      idempotency_key_hash char(64) NOT NULL,
      delivery_status text NOT NULL DEFAULT 'pending'
        CHECK (delivery_status IN ('pending','delivered','failed','dead_letter')),
      delivery_attempts integer NOT NULL DEFAULT 0,
      delivery_last_error text,
      odoo_event_id text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute(
        "CREATE UNIQUE INDEX uq_interaction_result_idem "
        "ON interaction_result(result_type, idempotency_key_hash)"
    )
    op.execute(
        "CREATE INDEX ix_interaction_result_interaction "
        "ON interaction_result(interaction_public_id)"
    )
    op.execute(
        "CREATE INDEX ix_interaction_result_delivery "
        "ON interaction_result(delivery_status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS interaction_result")
