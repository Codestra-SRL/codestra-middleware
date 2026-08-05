"""Telephony campaign, usage, security, and release-control metadata."""
from alembic import op

revision = "0071_telephony_sections_6_10_11_12"
down_revision = "0070_sections_7_9_platform"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE telephony_campaign_control (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, campaign_id varchar(128) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'DRAFT', timezone varchar(64) NOT NULL DEFAULT 'UTC', dialing_mode varchar(24) NOT NULL DEFAULT 'INTERNAL_TEST',
      max_lines integer NOT NULL DEFAULT 0, activation_approved boolean NOT NULL DEFAULT false, production_enabled boolean NOT NULL DEFAULT false,
      version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id, workspace_id, campaign_id, version)
    )""")
    op.execute("""CREATE TABLE telephony_suppression_check (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, phone_hash varchar(128) NOT NULL,
      scope varchar(24) NOT NULL DEFAULT 'TENANT', reason varchar(48) NOT NULL, suppressed boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE telephony_usage_record (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, usage_type varchar(64) NOT NULL,
      quantity bigint NOT NULL, unit varchar(32) NOT NULL, idempotency_key varchar(255) NOT NULL UNIQUE, billing_period varchar(32) NOT NULL DEFAULT 'UNASSIGNED', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE telephony_security_finding (
      id uuid PRIMARY KEY, component varchar(96) NOT NULL, severity varchar(16) NOT NULL, title varchar(255) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'OPEN', evidence_reference varchar(255) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE telephony_release_control (
      id uuid PRIMARY KEY, release_id varchar(128) NOT NULL UNIQUE, release_type varchar(48) NOT NULL, version varchar(64) NOT NULL,
      state varchar(32) NOT NULL DEFAULT 'DRAFT', backup_verified boolean NOT NULL DEFAULT false, rollback_verified boolean NOT NULL DEFAULT false,
      security_passed boolean NOT NULL DEFAULT false, routing_passed boolean NOT NULL DEFAULT false, monitoring_ready boolean NOT NULL DEFAULT false,
      production_approved boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for table in ("telephony_campaign_control", "telephony_suppression_check", "telephony_usage_record"):
        op.execute(f"CREATE INDEX ix_{table}_scope ON {table}(tenant_id,workspace_id)")


def downgrade() -> None:
    for table in ("telephony_release_control", "telephony_security_finding", "telephony_usage_record", "telephony_suppression_check", "telephony_campaign_control"):
        op.drop_table(table)
