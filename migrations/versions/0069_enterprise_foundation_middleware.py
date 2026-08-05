"""Enterprise foundation and middleware control-plane tables."""
from alembic import op

revision = "0069_enterprise_foundation_middleware"
down_revision = "0068_data_integration_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE core_service_registry (
      id uuid PRIMARY KEY, service_code varchar(96) NOT NULL UNIQUE, service_name varchar(160) NOT NULL,
      owner varchar(128) NOT NULL, environment varchar(32) NOT NULL DEFAULT 'STAGING', status varchar(24) NOT NULL DEFAULT 'UNKNOWN',
      version varchar(64) NOT NULL DEFAULT 'v1', health_endpoint varchar(255) NOT NULL DEFAULT '', created_by varchar(128) NOT NULL DEFAULT 'system',
      updated_by varchar(128) NOT NULL DEFAULT 'system', deleted_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE core_service_dependency (
      id uuid PRIMARY KEY, service_code varchar(96) NOT NULL, dependency_code varchar(96) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(service_code, dependency_code)
    )""")
    op.execute("""CREATE TABLE core_feature_flag (
      id uuid PRIMARY KEY, flag_key varchar(128) NOT NULL, tenant_id varchar(128) NOT NULL DEFAULT 'GLOBAL',
      workspace_id varchar(128) NOT NULL DEFAULT 'GLOBAL', enabled boolean NOT NULL DEFAULT false, version integer NOT NULL DEFAULT 1,
      created_by varchar(128) NOT NULL DEFAULT 'system', created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(flag_key, tenant_id, workspace_id)
    )""")
    op.execute("""CREATE TABLE core_command_record (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, command_type varchar(96) NOT NULL,
      idempotency_key varchar(255) NOT NULL UNIQUE, state varchar(24) NOT NULL DEFAULT 'RECEIVED', payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      actor_id varchar(128) NOT NULL, correlation_id varchar(128) NOT NULL, trace_id varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE core_event_record (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, event_type varchar(128) NOT NULL,
      schema_version varchar(32) NOT NULL DEFAULT '1.0', idempotency_key varchar(255) NOT NULL UNIQUE, payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
      actor_id varchar(128) NOT NULL, correlation_id varchar(128) NOT NULL, trace_id varchar(128) NOT NULL, state varchar(24) NOT NULL DEFAULT 'RECEIVED', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_core_command_scope ON core_command_record(tenant_id,workspace_id,state)")
    op.execute("CREATE INDEX ix_core_event_scope ON core_event_record(tenant_id,workspace_id,state)")


def downgrade() -> None:
    op.drop_index("ix_core_event_scope", table_name="core_event_record")
    op.drop_index("ix_core_command_scope", table_name="core_command_record")
    for table in ("core_event_record", "core_command_record", "core_feature_flag", "core_service_dependency", "core_service_registry"):
        op.drop_table(table)
