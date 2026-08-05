"""SaaS accounts, plans, provisioning and usage foundation."""
from alembic import op

revision = "0043_saas_foundation"
down_revision = "0042_executive_bi_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE saas_account (
      id uuid PRIMARY KEY, tenant_id varchar(128) UNIQUE NOT NULL, primary_workspace_id varchar(128), odoo_partner_id varchar(128),
      account_code varchar(64) UNIQUE NOT NULL, legal_name varchar(255) NOT NULL, display_name varchar(255) NOT NULL,
      status varchar(32) NOT NULL DEFAULT 'DRAFT', onboarding_mode varchar(32) NOT NULL, subscription_plan_id uuid,
      subscription_status varchar(32) NOT NULL DEFAULT 'DRAFT', billing_status varchar(32) NOT NULL DEFAULT 'NO_BILLING_REQUIRED',
      trial_started_at timestamptz, trial_expires_at timestamptz, activated_at timestamptz, suspended_at timestamptz, cancelled_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE saas_plan (
      id uuid PRIMARY KEY, code varchar(64) UNIQUE NOT NULL, display_name varchar(255) NOT NULL, version integer NOT NULL DEFAULT 1,
      status varchar(24) NOT NULL DEFAULT 'DRAFT', entitlements jsonb NOT NULL DEFAULT '{}', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE saas_provisioning_request (
      id uuid PRIMARY KEY, idempotency_key varchar(255) UNIQUE NOT NULL, onboarding_mode varchar(32) NOT NULL, plan_code varchar(64) NOT NULL,
      status varchar(40) NOT NULL DEFAULT 'REQUESTED', requested_by varchar(128) NOT NULL, correlation_id varchar(128) NOT NULL,
      tenant_id varchar(128), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE saas_usage_event (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128), meter_code varchar(96) NOT NULL,
      quantity integer NOT NULL, unit varchar(32) NOT NULL, period_start timestamptz NOT NULL, period_end timestamptz NOT NULL,
      source_service varchar(96) NOT NULL, source_event_id varchar(255) NOT NULL, idempotency_key varchar(255) UNIQUE NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_saas_account_status ON saas_account(status)")
    op.execute("CREATE INDEX ix_saas_provisioning_status ON saas_provisioning_request(status)")
    op.execute("CREATE INDEX ix_saas_usage_scope ON saas_usage_event(tenant_id, meter_code, period_end)")


def downgrade() -> None:
    op.drop_table("saas_usage_event")
    op.drop_table("saas_provisioning_request")
    op.drop_table("saas_plan")
    op.drop_table("saas_account")
