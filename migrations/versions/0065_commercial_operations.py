"""Commercial operations foundation."""
from alembic import op

revision = "0065_commercial_operations"
down_revision = "0064_named_customer_pilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE commercial_plan (
      id uuid PRIMARY KEY, plan_code varchar(64) NOT NULL UNIQUE, display_name varchar(128) NOT NULL,
      support_tier varchar(32) NOT NULL DEFAULT 'STANDARD', status varchar(24) NOT NULL DEFAULT 'DRAFT', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE commercial_subscription (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL UNIQUE, plan_code varchar(64) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'DRAFT', trial boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE commercial_entitlement (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      feature varchar(96) NOT NULL, limit_value bigint NOT NULL DEFAULT 0, state varchar(24) NOT NULL DEFAULT 'ACTIVE', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE commercial_usage_record (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      metric varchar(64) NOT NULL, quantity bigint NOT NULL, event_key varchar(160) NOT NULL UNIQUE,
      billing_period varchar(32) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE commercial_sla_instance (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, service varchar(96) NOT NULL,
      state varchar(24) NOT NULL DEFAULT 'NOT_STARTED', target_seconds bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_commercial_subscription_scope ON commercial_subscription(state,plan_code)")
    op.execute("CREATE INDEX ix_commercial_entitlement_scope ON commercial_entitlement(tenant_id,workspace_id,state)")
    op.execute("CREATE INDEX ix_commercial_usage_scope ON commercial_usage_record(tenant_id,workspace_id,billing_period)")
    op.execute("CREATE INDEX ix_commercial_sla_scope ON commercial_sla_instance(tenant_id,state)")


def downgrade() -> None:
    op.drop_index("ix_commercial_sla_scope", table_name="commercial_sla_instance")
    op.drop_index("ix_commercial_usage_scope", table_name="commercial_usage_record")
    op.drop_index("ix_commercial_entitlement_scope", table_name="commercial_entitlement")
    op.drop_index("ix_commercial_subscription_scope", table_name="commercial_subscription")
    op.drop_table("commercial_sla_instance")
    op.drop_table("commercial_usage_record")
    op.drop_table("commercial_entitlement")
    op.drop_table("commercial_subscription")
    op.drop_table("commercial_plan")
