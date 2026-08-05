"""Marketplace plugin registry and tenant installation foundation."""
from alembic import op

revision = "0044_marketplace_foundation"
down_revision = "0043_saas_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE marketplace_plugin (
      id uuid PRIMARY KEY, plugin_code varchar(96) UNIQUE NOT NULL, display_name varchar(255) NOT NULL,
      plugin_type varchar(64) NOT NULL, publisher_id varchar(128) NOT NULL, status varchar(32) NOT NULL DEFAULT 'DRAFT',
      description text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE marketplace_plugin_version (
      id uuid PRIMARY KEY, plugin_id uuid NOT NULL REFERENCES marketplace_plugin(id) ON DELETE RESTRICT,
      version varchar(32) NOT NULL, manifest jsonb NOT NULL, package_digest varchar(80) NOT NULL, signature varchar(512) NOT NULL,
      status varchar(32) NOT NULL DEFAULT 'DRAFT', created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_marketplace_plugin_version UNIQUE (plugin_id, version)
    )""")
    op.execute("""CREATE TABLE marketplace_tenant_installation (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, plugin_id uuid NOT NULL REFERENCES marketplace_plugin(id) ON DELETE RESTRICT,
      version varchar(32) NOT NULL, status varchar(32) NOT NULL DEFAULT 'INSTALLING', configuration jsonb NOT NULL DEFAULT '{}',
      idempotency_key varchar(255) NOT NULL, correlation_id varchar(128) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_marketplace_install_tenant_key UNIQUE (tenant_id, idempotency_key)
    )""")
    op.execute("CREATE INDEX ix_marketplace_plugin_status ON marketplace_plugin(status)")
    op.execute("CREATE INDEX ix_marketplace_install_tenant ON marketplace_tenant_installation(tenant_id, status)")


def downgrade() -> None:
    op.drop_table("marketplace_tenant_installation")
    op.drop_table("marketplace_plugin_version")
    op.drop_table("marketplace_plugin")
