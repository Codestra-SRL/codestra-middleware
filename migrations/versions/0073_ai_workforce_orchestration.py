"""Add durable AI workforce goals and teams."""

from alembic import op

revision = "0073_ai_workforce_orchestration"
down_revision = "0072_n8n_redis_orchestration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ai_employee_task ADD COLUMN goal_id uuid NULL")
    op.execute("ALTER TABLE ai_employee_task ADD COLUMN team_id uuid NULL")
    op.execute("ALTER TABLE ai_employee_task ADD COLUMN workflow_code varchar(128) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE ai_employee_task ADD COLUMN workflow_version varchar(64) NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE ai_employee_task ADD COLUMN trace_id varchar(128) NOT NULL DEFAULT ''")
    op.execute("CREATE INDEX ix_ai_employee_task_goal ON ai_employee_task(goal_id)")
    op.execute("CREATE INDEX ix_ai_employee_task_team ON ai_employee_task(team_id)")
    op.execute("""CREATE TABLE ai_workforce_goal (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      goal_code varchar(128) NOT NULL, owner_user_id varchar(128) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'DRAFT', target_reference varchar(255) NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (tenant_id, workspace_id, goal_code)
    )""")
    op.execute("""CREATE TABLE ai_workforce_team (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      team_code varchar(128) NOT NULL, department_id uuid NOT NULL, human_owner_user_id varchar(128) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'DRAFT', created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (tenant_id, workspace_id, team_code)
    )""")
    op.execute("CREATE INDEX ix_ai_workforce_goal_scope ON ai_workforce_goal(tenant_id, workspace_id, state)")
    op.execute("CREATE INDEX ix_ai_workforce_team_scope ON ai_workforce_team(tenant_id, workspace_id, state)")


def downgrade() -> None:
    op.drop_index("ix_ai_employee_task_team", table_name="ai_employee_task")
    op.drop_index("ix_ai_employee_task_goal", table_name="ai_employee_task")
    op.execute("ALTER TABLE ai_employee_task DROP COLUMN trace_id")
    op.execute("ALTER TABLE ai_employee_task DROP COLUMN workflow_version")
    op.execute("ALTER TABLE ai_employee_task DROP COLUMN workflow_code")
    op.execute("ALTER TABLE ai_employee_task DROP COLUMN team_id")
    op.execute("ALTER TABLE ai_employee_task DROP COLUMN goal_id")
    op.drop_index("ix_ai_workforce_team_scope", table_name="ai_workforce_team")
    op.drop_index("ix_ai_workforce_goal_scope", table_name="ai_workforce_goal")
    op.drop_table("ai_workforce_team")
    op.drop_table("ai_workforce_goal")
