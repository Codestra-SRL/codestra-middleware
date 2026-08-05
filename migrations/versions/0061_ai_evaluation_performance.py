"""AI evaluation, scorecard, and learning-control foundation."""
from alembic import op

revision = "0061_ai_evaluation_performance"
down_revision = "0060_ai_department_orchestration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE ai_employee_evaluation_run (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      employee_id varchar(128) NOT NULL, employee_version varchar(64) NOT NULL, dataset_version varchar(64) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'DRAFT', human_reviewed boolean NOT NULL DEFAULT false,
      trace_id varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_employee_scorecard (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      employee_id varchar(128) NOT NULL, period varchar(24) NOT NULL,
      performance_state varchar(32) NOT NULL DEFAULT 'UNASSESSED', evidence_count integer NOT NULL DEFAULT 0,
      reviewed boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (tenant_id,workspace_id,employee_id,period)
    )""")
    op.execute("""CREATE TABLE ai_employee_change_proposal (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      employee_id varchar(128) NOT NULL, proposal_type varchar(32) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'CAPTURED', proposed_by varchar(128) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_learning_approval (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, proposal_id uuid NOT NULL,
      reviewer_id varchar(128) NOT NULL, decision varchar(24) NOT NULL DEFAULT 'PENDING',
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_ai_employee_evaluation_run_scope ON ai_employee_evaluation_run(tenant_id,workspace_id,state)")
    op.execute("CREATE INDEX ix_ai_employee_scorecard_scope ON ai_employee_scorecard(tenant_id,workspace_id,employee_id)")
    op.execute("CREATE INDEX ix_ai_change_proposal_scope ON ai_employee_change_proposal(tenant_id,workspace_id,state)")
    op.execute("CREATE INDEX ix_ai_learning_approval_scope ON ai_learning_approval(tenant_id,proposal_id,decision)")


def downgrade() -> None:
    op.drop_index("ix_ai_learning_approval_scope", table_name="ai_learning_approval")
    op.drop_index("ix_ai_change_proposal_scope", table_name="ai_employee_change_proposal")
    op.drop_index("ix_ai_employee_scorecard_scope", table_name="ai_employee_scorecard")
    op.drop_index("ix_ai_employee_evaluation_run_scope", table_name="ai_employee_evaluation_run")
    op.drop_table("ai_learning_approval")
    op.drop_table("ai_employee_change_proposal")
    op.drop_table("ai_employee_scorecard")
    op.drop_table("ai_employee_evaluation_run")
