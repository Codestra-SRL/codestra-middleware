"""Data Factory, integration gateway, and commercial staging tables."""
from alembic import op

revision = "0070_sections_7_9_platform"
down_revision = "0069_enterprise_foundation_middleware"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE data_factory_source (
      id uuid PRIMARY KEY, source_code varchar(96) NOT NULL UNIQUE, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      authority_level varchar(24) NOT NULL DEFAULT 'CONTRIBUTING', schema_version varchar(32) NOT NULL DEFAULT 'v1', state varchar(24) NOT NULL DEFAULT 'DRAFT', classification varchar(24) NOT NULL DEFAULT 'INTERNAL', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE data_factory_ingestion_run (
      id uuid PRIMARY KEY, source_code varchar(96) NOT NULL, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      idempotency_key varchar(255) NOT NULL UNIQUE, records_received bigint NOT NULL DEFAULT 0, records_published bigint NOT NULL DEFAULT 0, state varchar(24) NOT NULL DEFAULT 'RECEIVED', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE data_factory_quality_result (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, ingestion_run_id uuid NOT NULL,
      dimension varchar(32) NOT NULL, outcome varchar(24) NOT NULL DEFAULT 'REVIEW_REQUIRED', evidence_reference varchar(255) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE master_entity_record (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, entity_type varchar(48) NOT NULL,
      authority_state varchar(24) NOT NULL DEFAULT 'REVIEW_REQUIRED', version integer NOT NULL DEFAULT 1, provenance_json jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE integration_connector_registry (
      id uuid PRIMARY KEY, connector_code varchar(96) NOT NULL UNIQUE, provider varchar(96) NOT NULL, version varchar(32) NOT NULL DEFAULT 'v1',
      capabilities_json jsonb NOT NULL DEFAULT '[]'::jsonb, sandbox_only boolean NOT NULL DEFAULT true, enabled boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE integration_gateway_request (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, connector_code varchar(96) NOT NULL,
      capability varchar(128) NOT NULL, idempotency_key varchar(255) NOT NULL UNIQUE, state varchar(32) NOT NULL DEFAULT 'REQUESTED', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE commercial_provisioning_request (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, subscription_id varchar(128) NOT NULL,
      idempotency_key varchar(255) NOT NULL UNIQUE, state varchar(32) NOT NULL DEFAULT 'PROVISIONING', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE commercial_billing_reference (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, billing_period varchar(32) NOT NULL, provider_reference varchar(255) NOT NULL,
      idempotency_key varchar(255) NOT NULL UNIQUE, state varchar(24) NOT NULL DEFAULT 'DRAFT', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for table in ("data_factory_source", "data_factory_ingestion_run", "data_factory_quality_result", "master_entity_record", "integration_gateway_request", "commercial_provisioning_request"):
        op.execute(f"CREATE INDEX ix_{table}_scope ON {table}(tenant_id,workspace_id)")


def downgrade() -> None:
    for table in ("commercial_billing_reference", "commercial_provisioning_request", "integration_gateway_request", "integration_connector_registry", "master_entity_record", "data_factory_quality_result", "data_factory_ingestion_run", "data_factory_source"):
        op.drop_table(table)
