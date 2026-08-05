"""Named customer pilot observation foundation."""
from alembic import op

revision = "0064_named_customer_pilot"
down_revision = "0063_ai_pilot_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE ai_named_customer_pilot (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL UNIQUE, state varchar(40) NOT NULL DEFAULT 'DRAFT',
      current_phase varchar(64) NOT NULL DEFAULT 'PHASE_0_PREPARATION', acceptance_status varchar(32) NOT NULL DEFAULT 'PENDING',
      evidence_complete boolean NOT NULL DEFAULT false, real_activation boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_named_pilot_observation_day (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, pilot_id uuid NOT NULL, day_number integer NOT NULL,
      status varchar(32) NOT NULL DEFAULT 'NO_DATA', review_completed boolean NOT NULL DEFAULT false,
      simulated boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (pilot_id,day_number)
    )""")
    op.execute("""CREATE TABLE ai_named_pilot_acceptance (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, pilot_id uuid NOT NULL,
      status varchar(32) NOT NULL DEFAULT 'PENDING', conditions varchar(1024) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_named_pilot_feedback (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, pilot_id uuid NOT NULL,
      category varchar(32) NOT NULL, status varchar(24) NOT NULL DEFAULT 'CAPTURED', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_ai_named_pilot_scope ON ai_named_customer_pilot(state,current_phase)")
    op.execute("CREATE INDEX ix_ai_named_observation_scope ON ai_named_pilot_observation_day(tenant_id,pilot_id,status)")
    op.execute("CREATE INDEX ix_ai_named_acceptance_scope ON ai_named_pilot_acceptance(tenant_id,pilot_id,status)")
    op.execute("CREATE INDEX ix_ai_named_feedback_scope ON ai_named_pilot_feedback(tenant_id,pilot_id,status)")


def downgrade() -> None:
    op.drop_index("ix_ai_named_feedback_scope", table_name="ai_named_pilot_feedback")
    op.drop_index("ix_ai_named_acceptance_scope", table_name="ai_named_pilot_acceptance")
    op.drop_index("ix_ai_named_observation_scope", table_name="ai_named_pilot_observation_day")
    op.drop_index("ix_ai_named_pilot_scope", table_name="ai_named_customer_pilot")
    op.drop_table("ai_named_pilot_feedback")
    op.drop_table("ai_named_pilot_acceptance")
    op.drop_table("ai_named_pilot_observation_day")
    op.drop_table("ai_named_customer_pilot")
