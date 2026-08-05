"""Developer Platform application, webhook and sandbox foundation."""
from alembic import op

revision = "0045_developer_platform_foundation"
down_revision = "0044_marketplace_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE developer_application (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, name varchar(255) NOT NULL,
      client_type varchar(24) NOT NULL, scopes jsonb NOT NULL, status varchar(24) NOT NULL DEFAULT 'ACTIVE',
      correlation_id varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE developer_webhook_subscription (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, event_type varchar(96) NOT NULL,
      endpoint_url varchar(512) NOT NULL, secret_reference varchar(255) NOT NULL, status varchar(24) NOT NULL DEFAULT 'ACTIVE',
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE developer_sandbox (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, environment varchar(24) NOT NULL DEFAULT 'sandbox',
      status varchar(24) NOT NULL DEFAULT 'PROVISIONING', idempotency_key varchar(255) UNIQUE NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_developer_app_tenant ON developer_application(tenant_id)")
    op.execute("CREATE INDEX ix_developer_webhook_tenant ON developer_webhook_subscription(tenant_id)")
    op.execute("CREATE INDEX ix_developer_sandbox_tenant ON developer_sandbox(tenant_id)")


def downgrade() -> None:
    op.drop_table("developer_sandbox")
    op.drop_table("developer_webhook_subscription")
    op.drop_table("developer_application")
