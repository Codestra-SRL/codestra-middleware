"""IAM, governance, integration, data, and DR evidence foundation."""

from alembic import op

revision = "0053_enterprise_phases_foundation"
down_revision = "0052_revops_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE enterprise_identity_provider (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, provider_type varchar(24) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'STAGING', credential_reference varchar(255) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE governance_evidence (
      id uuid PRIMARY KEY, tenant_id varchar(128), control_code varchar(96) NOT NULL,
      evidence_hash varchar(128) NOT NULL, status varchar(24) NOT NULL DEFAULT 'COLLECTED', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE integration_webhook_event (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, provider varchar(64) NOT NULL,
      idempotency_key varchar(255) NOT NULL UNIQUE, status varchar(24) NOT NULL DEFAULT 'RECEIVED', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE data_pipeline_run (
      id uuid PRIMARY KEY, tenant_id varchar(128), source varchar(96) NOT NULL, status varchar(24) NOT NULL DEFAULT 'STAGING',
      row_scope_enforced boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE disaster_recovery_evidence (
      id uuid PRIMARY KEY, service varchar(96) NOT NULL, encrypted boolean NOT NULL DEFAULT false,
      off_server boolean NOT NULL DEFAULT false, checksum varchar(128) NOT NULL DEFAULT '', restore_status varchar(24) NOT NULL DEFAULT 'UNVERIFIED', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for index, table, columns in (
        ("ix_enterprise_identity_tenant", "enterprise_identity_provider", "tenant_id"),
        ("ix_governance_evidence_scope", "governance_evidence", "tenant_id,control_code"),
        ("ix_integration_webhook_scope", "integration_webhook_event", "tenant_id,provider"),
        ("ix_data_pipeline_scope", "data_pipeline_run", "tenant_id,source"),
        ("ix_dr_evidence_service", "disaster_recovery_evidence", "service,restore_status"),
    ):
        op.execute(f"CREATE INDEX {index} ON {table} ({columns})")


def downgrade() -> None:
    for index, table in (
        ("ix_dr_evidence_service", "disaster_recovery_evidence"),
        ("ix_data_pipeline_scope", "data_pipeline_run"),
        ("ix_integration_webhook_scope", "integration_webhook_event"),
        ("ix_governance_evidence_scope", "governance_evidence"),
        ("ix_enterprise_identity_tenant", "enterprise_identity_provider"),
    ):
        op.drop_index(index, table_name=table)
    for table in ("disaster_recovery_evidence", "data_pipeline_run", "integration_webhook_event", "governance_evidence", "enterprise_identity_provider"):
        op.drop_table(table)
