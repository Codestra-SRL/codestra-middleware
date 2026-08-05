"""Executive Control Tower foundation."""
from alembic import op

revision = "0062_control_tower"
down_revision = "0061_ai_evaluation_performance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE control_tower_service (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, service_code varchar(96) NOT NULL,
      server varchar(64) NOT NULL, criticality varchar(24) NOT NULL DEFAULT 'STANDARD',
      state varchar(24) NOT NULL DEFAULT 'UNKNOWN', last_success timestamptz NULL, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (tenant_id,service_code)
    )""")
    op.execute("""CREATE TABLE control_tower_kpi (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, name varchar(128) NOT NULL,
      formula varchar(512) NOT NULL, source varchar(128) NOT NULL, version varchar(32) NOT NULL,
      freshness varchar(24) NOT NULL DEFAULT 'UNKNOWN', value varchar(128) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE control_tower_incident (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, severity varchar(16) NOT NULL DEFAULT 'MEDIUM',
      incident_type varchar(32) NOT NULL, state varchar(24) NOT NULL DEFAULT 'DETECTED', owner_id varchar(128) NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE control_tower_action (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      actor_id varchar(128) NOT NULL, action varchar(64) NOT NULL, state varchar(24) NOT NULL DEFAULT 'REQUESTED',
      idempotency_key varchar(160) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_control_tower_service_scope ON control_tower_service(tenant_id,state)")
    op.execute("CREATE INDEX ix_control_tower_kpi_scope ON control_tower_kpi(tenant_id,freshness)")
    op.execute("CREATE INDEX ix_control_tower_incident_scope ON control_tower_incident(tenant_id,state,severity)")
    op.execute("CREATE INDEX ix_control_tower_action_scope ON control_tower_action(tenant_id,workspace_id,state)")


def downgrade() -> None:
    op.drop_index("ix_control_tower_action_scope", table_name="control_tower_action")
    op.drop_index("ix_control_tower_incident_scope", table_name="control_tower_incident")
    op.drop_index("ix_control_tower_kpi_scope", table_name="control_tower_kpi")
    op.drop_index("ix_control_tower_service_scope", table_name="control_tower_service")
    op.drop_table("control_tower_action")
    op.drop_table("control_tower_incident")
    op.drop_table("control_tower_kpi")
    op.drop_table("control_tower_service")
