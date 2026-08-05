"""Governed AI Tool Gateway foundation."""
from alembic import op

revision = "0059_ai_tool_framework"
down_revision = "0058_ai_memory_knowledge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE ai_tool (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, tool_code varchar(128) NOT NULL,
      adapter varchar(96) NOT NULL, version varchar(64) NOT NULL, risk_level varchar(24) NOT NULL DEFAULT 'READ_ONLY',
      required_approval boolean NOT NULL DEFAULT false, enabled boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (tenant_id,tool_code,version)
    )""")
    op.execute("""CREATE TABLE ai_tool_request (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      employee_id varchar(128) NOT NULL, task_id varchar(128) NOT NULL, tool_code varchar(128) NOT NULL,
      action varchar(128) NOT NULL, state varchar(32) NOT NULL DEFAULT 'REQUESTED',
      idempotency_key varchar(160) NOT NULL UNIQUE, trace_id varchar(128) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_tool_execution (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, request_id uuid NOT NULL,
      attempt integer NOT NULL DEFAULT 0, state varchar(32) NOT NULL DEFAULT 'QUEUED',
      external_reference varchar(255) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_tool_reconciliation (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, request_id uuid NOT NULL,
      outcome varchar(32) NOT NULL DEFAULT 'UNKNOWN', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_ai_tool_scope ON ai_tool(tenant_id,tool_code,enabled)")
    op.execute("CREATE INDEX ix_ai_tool_request_scope ON ai_tool_request(tenant_id,workspace_id,state)")
    op.execute("CREATE INDEX ix_ai_tool_execution_scope ON ai_tool_execution(tenant_id,request_id,state)")
    op.execute("CREATE INDEX ix_ai_tool_reconciliation_scope ON ai_tool_reconciliation(tenant_id,request_id,outcome)")


def downgrade() -> None:
    op.drop_index("ix_ai_tool_reconciliation_scope", table_name="ai_tool_reconciliation")
    op.drop_index("ix_ai_tool_execution_scope", table_name="ai_tool_execution")
    op.drop_index("ix_ai_tool_request_scope", table_name="ai_tool_request")
    op.drop_index("ix_ai_tool_scope", table_name="ai_tool")
    op.drop_table("ai_tool_reconciliation")
    op.drop_table("ai_tool_execution")
    op.drop_table("ai_tool_request")
    op.drop_table("ai_tool")
