"""AI department orchestration foundation."""
from alembic import op

revision = "0060_ai_department_orchestration"
down_revision = "0059_ai_tool_framework"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE ai_department (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      department_code varchar(64) NOT NULL, state varchar(32) NOT NULL DEFAULT 'DRAFT',
      human_manager_id varchar(128) NOT NULL, ai_manager_id varchar(128) NOT NULL DEFAULT '',
      budget_limit bigint NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (tenant_id,workspace_id,department_code)
    )""")
    op.execute("""CREATE TABLE ai_collaboration_session (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      goal_id varchar(128) NOT NULL, owning_department_id uuid NOT NULL, manager_employee_id varchar(128) NOT NULL,
      human_owner_user_id varchar(128) NOT NULL, status varchar(32) NOT NULL DEFAULT 'DRAFT',
      participant_limit integer NOT NULL DEFAULT 8, delegation_depth_limit integer NOT NULL DEFAULT 3,
      trace_id varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_delegation (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      collaboration_id uuid NOT NULL, source_employee_id varchar(128) NOT NULL, target_employee_id varchar(128) NOT NULL,
      depth integer NOT NULL DEFAULT 1, state varchar(32) NOT NULL DEFAULT 'DRAFT',
      idempotency_key varchar(160) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_handoff (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      collaboration_id uuid NOT NULL, sender_employee_id varchar(128) NOT NULL, receiver_employee_id varchar(128) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'DRAFT', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_ai_department_scope ON ai_department(tenant_id,workspace_id,state)")
    op.execute("CREATE INDEX ix_ai_collaboration_scope ON ai_collaboration_session(tenant_id,workspace_id,status)")
    op.execute("CREATE INDEX ix_ai_delegation_scope ON ai_delegation(tenant_id,workspace_id,state)")
    op.execute("CREATE INDEX ix_ai_handoff_scope ON ai_handoff(tenant_id,workspace_id,state)")


def downgrade() -> None:
    op.drop_index("ix_ai_handoff_scope", table_name="ai_handoff")
    op.drop_index("ix_ai_delegation_scope", table_name="ai_delegation")
    op.drop_index("ix_ai_collaboration_scope", table_name="ai_collaboration_session")
    op.drop_index("ix_ai_department_scope", table_name="ai_department")
    op.drop_table("ai_handoff")
    op.drop_table("ai_delegation")
    op.drop_table("ai_collaboration_session")
    op.drop_table("ai_department")
