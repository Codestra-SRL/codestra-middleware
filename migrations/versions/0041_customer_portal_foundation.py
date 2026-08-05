"""Customer Portal tenant and user foundation."""
from alembic import op

revision = "0041_customer_portal_foundation"
down_revision = "0040_controlled_expansion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE customer_account (
      id uuid PRIMARY KEY, tenant_id varchar(128) UNIQUE NOT NULL, workspace_id varchar(128) NOT NULL,
      odoo_partner_id varchar(128), status varchar(24) NOT NULL DEFAULT 'INVITED', subscription_plan varchar(64),
      allowed_modules jsonb NOT NULL DEFAULT '[]', primary_contact varchar(255), billing_contact varchar(255),
      support_contact varchar(255), retention_policy jsonb NOT NULL DEFAULT '{}',
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE customer_user (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      email varchar(320) NOT NULL, display_name varchar(255) NOT NULL, role varchar(32) NOT NULL DEFAULT 'CUSTOMER_READ_ONLY',
      status varchar(24) NOT NULL DEFAULT 'INVITED', email_verified_at timestamptz, mfa_enabled boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      CONSTRAINT uq_customer_user_tenant_email UNIQUE (tenant_id, email)
    )""")
    op.execute("CREATE INDEX ix_customer_user_tenant ON customer_user(tenant_id)")
    op.execute("CREATE INDEX ix_customer_user_workspace ON customer_user(workspace_id)")


def downgrade() -> None:
    op.drop_table("customer_user")
    op.drop_table("customer_account")
