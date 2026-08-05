"""Sales, marketing, and revenue-operations foundation."""

from alembic import op

revision = "0052_revops_foundation"
down_revision = "0051_support_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE revops_lead (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, display_name varchar(255) NOT NULL,
      source varchar(96) NOT NULL DEFAULT '', idempotency_key varchar(255) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE revops_opportunity (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, lead_id varchar(128) NOT NULL, name varchar(255) NOT NULL,
      status varchar(32) NOT NULL DEFAULT 'NEW', idempotency_key varchar(255) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE revops_campaign (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, name varchar(255) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'DRAFT', idempotency_key varchar(255) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE revops_commission (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, opportunity_id varchar(128) NOT NULL,
      amount_minor bigint NOT NULL DEFAULT 0, status varchar(24) NOT NULL DEFAULT 'PENDING_REVIEW', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for index, table, columns in (
        ("ix_revops_lead_tenant", "revops_lead", "tenant_id"),
        ("ix_revops_opportunity_scope", "revops_opportunity", "tenant_id,status"),
        ("ix_revops_campaign_scope", "revops_campaign", "tenant_id,status"),
        ("ix_revops_commission_scope", "revops_commission", "tenant_id,status"),
    ):
        op.execute(f"CREATE INDEX {index} ON {table} ({columns})")


def downgrade() -> None:
    for index, table in (
        ("ix_revops_commission_scope", "revops_commission"),
        ("ix_revops_campaign_scope", "revops_campaign"),
        ("ix_revops_opportunity_scope", "revops_opportunity"),
        ("ix_revops_lead_tenant", "revops_lead"),
    ):
        op.drop_index(index, table_name=table)
    for table in ("revops_commission", "revops_campaign", "revops_opportunity", "revops_lead"):
        op.drop_table(table)
