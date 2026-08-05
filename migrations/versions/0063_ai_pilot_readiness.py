"""Named-tenant AI Workforce pilot foundation."""
from alembic import op

revision = "0063_ai_pilot_readiness"
down_revision = "0062_control_tower"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE ai_pilot_program (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, name varchar(128) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'PROPOSED', max_tenants integer NOT NULL DEFAULT 3,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_pilot_admission (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      employee_id varchar(128) NOT NULL, autonomy_level varchar(32) NOT NULL, human_owner_id varchar(128) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'VALIDATING', budget_limit bigint NOT NULL DEFAULT 0,
      suspended boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_pilot_readiness_check (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, admission_id uuid NOT NULL,
      gate varchar(48) NOT NULL, outcome varchar(24) NOT NULL DEFAULT 'BLOCKED',
      evidence_reference varchar(255) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_pilot_suspension (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, admission_id uuid NOT NULL,
      operator_id varchar(128) NOT NULL, reason varchar(512) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_ai_pilot_program_scope ON ai_pilot_program(tenant_id,state)")
    op.execute("CREATE INDEX ix_ai_pilot_admission_scope ON ai_pilot_admission(tenant_id,workspace_id,state)")
    op.execute("CREATE INDEX ix_ai_pilot_readiness_scope ON ai_pilot_readiness_check(tenant_id,admission_id,outcome)")
    op.execute("CREATE INDEX ix_ai_pilot_suspension_scope ON ai_pilot_suspension(tenant_id,admission_id)")


def downgrade() -> None:
    op.drop_index("ix_ai_pilot_suspension_scope", table_name="ai_pilot_suspension")
    op.drop_index("ix_ai_pilot_readiness_scope", table_name="ai_pilot_readiness_check")
    op.drop_index("ix_ai_pilot_admission_scope", table_name="ai_pilot_admission")
    op.drop_index("ix_ai_pilot_program_scope", table_name="ai_pilot_program")
    op.drop_table("ai_pilot_suspension")
    op.drop_table("ai_pilot_readiness_check")
    op.drop_table("ai_pilot_admission")
    op.drop_table("ai_pilot_program")
