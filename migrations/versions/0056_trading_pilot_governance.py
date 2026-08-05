"""Trading licensing gaps and controlled pilot governance foundation."""

from alembic import op

revision = "0056_trading_pilot_governance"
down_revision = "0055_trading_readiness_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE trading_licensing_gap (
      id uuid PRIMARY KEY, category varchar(64) NOT NULL, classification varchar(32) NOT NULL,
      jurisdiction varchar(96) NOT NULL DEFAULT 'UNKNOWN', evidence_reference varchar(255) NOT NULL DEFAULT '',
      status varchar(24) NOT NULL DEFAULT 'OPEN', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE trading_pilot_approval (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, account_id varchar(128) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'DRAFT', synthetic_only boolean NOT NULL DEFAULT true,
      legal_approval boolean NOT NULL DEFAULT false, security_approval boolean NOT NULL DEFAULT false,
      compliance_approval boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE trading_pilot_evidence (
      id uuid PRIMARY KEY, pilot_id varchar(128) NOT NULL, evidence_type varchar(64) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'MISSING', reference varchar(255) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_trading_licensing_gap_scope ON trading_licensing_gap(jurisdiction,classification,status)")
    op.execute("CREATE INDEX ix_trading_pilot_approval_scope ON trading_pilot_approval(tenant_id,account_id,state)")
    op.execute("CREATE INDEX ix_trading_pilot_evidence_scope ON trading_pilot_evidence(pilot_id,status)")


def downgrade() -> None:
    op.drop_index("ix_trading_pilot_evidence_scope", table_name="trading_pilot_evidence")
    op.drop_index("ix_trading_pilot_approval_scope", table_name="trading_pilot_approval")
    op.drop_index("ix_trading_licensing_gap_scope", table_name="trading_licensing_gap")
    op.drop_table("trading_pilot_evidence")
    op.drop_table("trading_pilot_approval")
    op.drop_table("trading_licensing_gap")
