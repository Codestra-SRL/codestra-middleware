"""Executive BI KPI definitions and observations."""
from alembic import op

revision = "0042_executive_bi_foundation"
down_revision = "0041_customer_portal_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE kpi_definition (
      id uuid PRIMARY KEY, code varchar(96) NOT NULL, version integer NOT NULL DEFAULT 1,
      name varchar(255) NOT NULL, definition text NOT NULL, formula varchar(512) NOT NULL,
      source_reference varchar(255) NOT NULL, owner varchar(96) NOT NULL, status varchar(24) NOT NULL DEFAULT 'DRAFT',
      guardrails jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_kpi_definition_version UNIQUE (code, version)
    )""")
    op.execute("""CREATE TABLE kpi_observation (
      id uuid PRIMARY KEY, tenant_id varchar(128), workspace_id varchar(128), kpi_code varchar(96) NOT NULL,
      period_start timestamptz NOT NULL, period_end timestamptz NOT NULL, value integer NOT NULL,
      numerator integer, denominator integer, source_freshness timestamptz, quality_status varchar(24) NOT NULL DEFAULT 'UNVERIFIED',
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_kpi_observation_scope ON kpi_observation(tenant_id, workspace_id, kpi_code, period_end)")


def downgrade() -> None:
    op.drop_table("kpi_observation")
    op.drop_table("kpi_definition")
