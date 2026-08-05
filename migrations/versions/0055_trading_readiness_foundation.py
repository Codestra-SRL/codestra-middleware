"""Trading sandbox, compliance, and readiness foundation."""

from alembic import op

revision = "0055_trading_readiness_foundation"
down_revision = "0054_trading_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE trading_provider_connection (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, provider varchar(96) NOT NULL,
      environment varchar(24) NOT NULL DEFAULT 'SANDBOX', credential_reference varchar(255) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'PENDING', allowed_operations varchar(512) NOT NULL DEFAULT 'health_check', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE trading_contract_certification (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, symbol varchar(32) NOT NULL, source varchar(96) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'PENDING', evidence_reference varchar(255) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE trading_provider_reconciliation (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, entity_type varchar(32) NOT NULL,
      internal_reference varchar(255) NOT NULL, provider_reference varchar(255) NOT NULL DEFAULT '', outcome varchar(32) NOT NULL DEFAULT 'UNKNOWN', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE trading_compliance_review (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, account_id varchar(128) NOT NULL,
      review_type varchar(32) NOT NULL, status varchar(24) NOT NULL DEFAULT 'PENDING', synthetic boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE trading_disclosure_acceptance (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, account_id varchar(128) NOT NULL,
      disclosure_code varchar(64) NOT NULL, version varchar(32) NOT NULL, accepted boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for index, table, columns in (
        ("ix_trading_provider_scope", "trading_provider_connection", "tenant_id,status"),
        ("ix_trading_contract_scope", "trading_contract_certification", "tenant_id,symbol,status"),
        ("ix_trading_reconciliation_scope", "trading_provider_reconciliation", "tenant_id,entity_type,outcome"),
        ("ix_trading_compliance_scope", "trading_compliance_review", "tenant_id,account_id,status"),
        ("ix_trading_disclosure_scope", "trading_disclosure_acceptance", "tenant_id,account_id"),
    ):
        op.execute(f"CREATE INDEX {index} ON {table} ({columns})")


def downgrade() -> None:
    for index, table in (
        ("ix_trading_disclosure_scope", "trading_disclosure_acceptance"),
        ("ix_trading_compliance_scope", "trading_compliance_review"),
        ("ix_trading_reconciliation_scope", "trading_provider_reconciliation"),
        ("ix_trading_contract_scope", "trading_contract_certification"),
        ("ix_trading_provider_scope", "trading_provider_connection"),
    ):
        op.drop_index(index, table_name=table)
    for table in ("trading_disclosure_acceptance", "trading_compliance_review", "trading_provider_reconciliation", "trading_contract_certification", "trading_provider_connection"):
        op.drop_table(table)
