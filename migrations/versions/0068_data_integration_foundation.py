"""Enterprise data and integration foundation."""
from alembic import op

revision = "0068_data_integration_foundation"
down_revision = "0067_business_os"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE enterprise_data_record (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      entity_type varchar(64) NOT NULL, entity_key varchar(160) NOT NULL, classification varchar(24) NOT NULL DEFAULT 'INTERNAL',
      source_system varchar(96) NOT NULL, source_version varchar(64) NOT NULL DEFAULT 'v1', created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (tenant_id,workspace_id,entity_type,entity_key)
    )""")
    op.execute("""CREATE TABLE data_lineage_record (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, source_reference varchar(255) NOT NULL,
      target_reference varchar(255) NOT NULL, transformation varchar(255) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE integration_connector (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, connector_code varchar(96) NOT NULL,
      version varchar(64) NOT NULL, state varchar(24) NOT NULL DEFAULT 'DRAFT', sandbox_only boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (tenant_id,connector_code,version)
    )""")
    op.execute("""CREATE TABLE enterprise_integration_event (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      connector_code varchar(96) NOT NULL, idempotency_key varchar(160) NOT NULL UNIQUE, state varchar(32) NOT NULL DEFAULT 'RECEIVED', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_enterprise_data_scope ON enterprise_data_record(tenant_id,workspace_id,entity_type)")
    op.execute("CREATE INDEX ix_data_lineage_scope ON data_lineage_record(tenant_id,source_reference)")
    op.execute("CREATE INDEX ix_integration_connector_scope ON integration_connector(tenant_id,connector_code,state)")
    op.execute("CREATE INDEX ix_integration_event_scope ON enterprise_integration_event(tenant_id,workspace_id,state)")


def downgrade() -> None:
    op.drop_index("ix_integration_event_scope", table_name="enterprise_integration_event")
    op.drop_index("ix_integration_connector_scope", table_name="integration_connector")
    op.drop_index("ix_data_lineage_scope", table_name="data_lineage_record")
    op.drop_index("ix_enterprise_data_scope", table_name="enterprise_data_record")
    op.drop_table("enterprise_integration_event")
    op.drop_table("integration_connector")
    op.drop_table("data_lineage_record")
    op.drop_table("enterprise_data_record")
