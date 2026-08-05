"""Mobile device, push and sync foundation."""
from alembic import op

revision = "0046_mobile_platform_foundation"
down_revision = "0045_developer_platform_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE mobile_device (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, user_reference varchar(128) NOT NULL,
      platform varchar(16) NOT NULL, app_version varchar(32) NOT NULL, device_hash varchar(128) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'PENDING', last_active_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE mobile_push_token (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, device_id uuid, token_reference varchar(255) NOT NULL,
      platform varchar(16) NOT NULL, status varchar(24) NOT NULL DEFAULT 'ACTIVE', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE mobile_sync_session (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, client_session_id varchar(128) NOT NULL,
      item_count integer NOT NULL DEFAULT 0, status varchar(24) NOT NULL DEFAULT 'PENDING', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_mobile_device_tenant_status ON mobile_device(tenant_id, status)")
    op.execute("CREATE INDEX ix_mobile_push_tenant_status ON mobile_push_token(tenant_id, status)")
    op.execute("CREATE INDEX ix_mobile_sync_tenant_status ON mobile_sync_session(tenant_id, status)")


def downgrade() -> None:
    op.drop_table("mobile_sync_session")
    op.drop_table("mobile_push_token")
    op.drop_table("mobile_device")
