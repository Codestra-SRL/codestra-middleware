"""Forex and crypto paper/demo trading foundation."""

from alembic import op

revision = "0054_trading_foundation"
down_revision = "0053_enterprise_phases_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE trading_account (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, customer_id varchar(128) NOT NULL,
      account_type varchar(32) NOT NULL, base_currency varchar(16) NOT NULL DEFAULT 'USD',
      status varchar(24) NOT NULL DEFAULT 'ACTIVE', idempotency_key varchar(255) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE trading_instrument (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, symbol varchar(32) NOT NULL,
      asset_class varchar(16) NOT NULL, status varchar(24) NOT NULL DEFAULT 'ACTIVE', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE trading_order (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, account_id varchar(128) NOT NULL, instrument_id varchar(128) NOT NULL,
      side varchar(8) NOT NULL, order_type varchar(24) NOT NULL, status varchar(32) NOT NULL DEFAULT 'DRAFT',
      idempotency_key varchar(255) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE trading_ledger_entry (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, account_id varchar(128) NOT NULL, entry_type varchar(32) NOT NULL,
      debit_minor bigint NOT NULL DEFAULT 0, credit_minor bigint NOT NULL DEFAULT 0, external_reference varchar(255) NOT NULL UNIQUE,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for index, table, columns in (
        ("ix_trading_account_scope", "trading_account", "tenant_id,status"),
        ("ix_trading_instrument_scope", "trading_instrument", "tenant_id,status"),
        ("ix_trading_order_scope", "trading_order", "tenant_id,account_id,status"),
        ("ix_trading_ledger_scope", "trading_ledger_entry", "tenant_id,account_id"),
    ):
        op.execute(f"CREATE INDEX {index} ON {table} ({columns})")


def downgrade() -> None:
    for index, table in (
        ("ix_trading_ledger_scope", "trading_ledger_entry"),
        ("ix_trading_order_scope", "trading_order"),
        ("ix_trading_instrument_scope", "trading_instrument"),
        ("ix_trading_account_scope", "trading_account"),
    ):
        op.drop_index(index, table_name=table)
    for table in ("trading_ledger_entry", "trading_order", "trading_instrument", "trading_account"):
        op.drop_table(table)
