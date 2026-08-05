"""Fail-closed campaign activation and one-call canary governance."""
from alembic import op

revision = "0037_vicidial_campaign_canary"
down_revision = "0036_vicidial_assignment_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE vicidial_campaign_activation_approval (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128),
      campaign_id varchar(128) NOT NULL, list_id varchar(128) NOT NULL,
      status varchar(32) NOT NULL DEFAULT 'REQUESTED', requested_by varchar(128) NOT NULL,
      approved_by varchar(128), authorization_reference varchar(255),
      maintenance_window_start timestamptz NOT NULL, maintenance_window_end timestamptz NOT NULL,
      reason varchar(1024) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      approved_at timestamptz, activated_at timestamptz, shut_down_at timestamptz,
      UNIQUE(tenant_id, campaign_id, list_id, maintenance_window_start)
    )""")
    op.execute("""CREATE TABLE vicidial_dialing_window_policy (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128),
      policy_code varchar(96) NOT NULL, timezone varchar(64) NOT NULL,
      start_local varchar(8) NOT NULL, end_local varchar(8) NOT NULL,
      max_agents integer NOT NULL DEFAULT 1, max_calls integer NOT NULL DEFAULT 1,
      status varchar(24) NOT NULL DEFAULT 'TESTING', created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(tenant_id, workspace_id, policy_code)
    )""")
    op.execute("""CREATE TABLE vicidial_canary_run (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL,
      approval_id uuid NOT NULL REFERENCES vicidial_campaign_activation_approval(id) ON DELETE RESTRICT,
      assignment_item_id uuid NOT NULL REFERENCES vicidial_assignment_item(id) ON DELETE RESTRICT,
      allowlisted_phone_hash char(64) NOT NULL, status varchar(32) NOT NULL DEFAULT 'AUTHORIZED',
      agent_reference varchar(128), carrier_check varchar(24) NOT NULL DEFAULT 'PENDING',
      dialing_window_check varchar(24) NOT NULL DEFAULT 'PENDING', call_count integer NOT NULL DEFAULT 0,
      call_result jsonb, created_at timestamptz NOT NULL DEFAULT now(), activated_at timestamptz,
      stopped_at timestamptz, completed_at timestamptz
    )""")
    op.execute("""CREATE TABLE vicidial_canary_event (
      id uuid PRIMARY KEY, canary_run_id uuid NOT NULL REFERENCES vicidial_canary_run(id) ON DELETE RESTRICT,
      event_type varchar(64) NOT NULL, payload_safe jsonb NOT NULL, correlation_id varchar(128) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_vicidial_canary_approval_status ON vicidial_campaign_activation_approval(tenant_id, status)")
    op.execute("CREATE INDEX ix_vicidial_canary_run_status ON vicidial_canary_run(tenant_id, status)")


def downgrade() -> None:
    for table in ("vicidial_canary_event", "vicidial_canary_run", "vicidial_dialing_window_policy", "vicidial_campaign_activation_approval"):
        op.drop_table(table)
