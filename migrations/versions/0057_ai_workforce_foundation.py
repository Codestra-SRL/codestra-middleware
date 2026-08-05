"""Governed AI Workforce foundation."""

from alembic import op

revision = "0057_ai_workforce_foundation"
down_revision = "0056_trading_pilot_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE ai_employee (
      id uuid PRIMARY KEY, employee_code varchar(96) NOT NULL UNIQUE,
      tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      display_name varchar(160) NOT NULL, employee_type varchar(64) NOT NULL,
      status varchar(32) NOT NULL DEFAULT 'DRAFT', configuration_version integer NOT NULL DEFAULT 1,
      human_owner_user_id varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_employee_task (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      employee_id uuid NOT NULL, state varchar(32) NOT NULL DEFAULT 'DRAFT',
      idempotency_key varchar(160) NOT NULL UNIQUE, approval_required boolean NOT NULL DEFAULT true,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_employee_tool (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, tool_code varchar(96) NOT NULL,
      risk_level varchar(24) NOT NULL DEFAULT 'READ_ONLY', required_approval boolean NOT NULL DEFAULT false,
      enabled boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_employee_approval (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, task_id uuid NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'PENDING', reviewer_id varchar(128) NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_employee_memory (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      employee_id uuid NOT NULL, classification varchar(24) NOT NULL DEFAULT 'INTERNAL',
      approved boolean NOT NULL DEFAULT false, expires_at timestamptz NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_employee_delegation (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, source_employee_id uuid NOT NULL,
      target_employee_id uuid NOT NULL, depth integer NOT NULL DEFAULT 1, collaborator_count integer NOT NULL DEFAULT 1,
      status varchar(24) NOT NULL DEFAULT 'PENDING', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_ai_employee_scope ON ai_employee(tenant_id,workspace_id,status)")
    op.execute("CREATE INDEX ix_ai_employee_task_scope ON ai_employee_task(tenant_id,workspace_id,state)")
    op.execute("CREATE INDEX ix_ai_employee_tool_scope ON ai_employee_tool(tenant_id,tool_code)")
    op.execute("CREATE INDEX ix_ai_employee_approval_scope ON ai_employee_approval(tenant_id,task_id,status)")
    op.execute("CREATE INDEX ix_ai_employee_memory_scope ON ai_employee_memory(tenant_id,workspace_id,employee_id)")
    op.execute("CREATE INDEX ix_ai_employee_delegation_scope ON ai_employee_delegation(tenant_id,status)")


def downgrade() -> None:
    for index, table in (
        ("ix_ai_employee_delegation_scope", "ai_employee_delegation"),
        ("ix_ai_employee_memory_scope", "ai_employee_memory"),
        ("ix_ai_employee_approval_scope", "ai_employee_approval"),
        ("ix_ai_employee_tool_scope", "ai_employee_tool"),
        ("ix_ai_employee_task_scope", "ai_employee_task"),
        ("ix_ai_employee_scope", "ai_employee"),
    ):
        op.drop_index(index, table_name=table)
    for table in ("ai_employee_delegation", "ai_employee_memory", "ai_employee_approval", "ai_employee_tool", "ai_employee_task", "ai_employee"):
        op.drop_table(table)
