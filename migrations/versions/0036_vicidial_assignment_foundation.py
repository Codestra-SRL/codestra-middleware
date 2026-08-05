"""Controlled, disabled-by-default Odoo-to-VICIdial assignment state."""

from alembic import op

revision = "0036_vicidial_assignment_foundation"
down_revision = "0035_human_approval_odoo_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE vicidial_assignment_policy (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128), policy_code varchar(96) NOT NULL,
      version integer NOT NULL, configuration jsonb NOT NULL, status varchar(24) NOT NULL DEFAULT 'TESTING', approved_by varchar(128), approved_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id, workspace_id, policy_code, version)
    )""")
    op.execute("""CREATE TABLE vicidial_assignment_batch (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128), batch_code varchar(128) NOT NULL UNIQUE,
      policy_id uuid, target_campaign_id varchar(128) NOT NULL, target_list_id varchar(128) NOT NULL, status varchar(32) NOT NULL DEFAULT 'REQUESTED',
      requested_by varchar(128) NOT NULL, approved_by varchar(128), idempotency_key varchar(255) NOT NULL, correlation_id varchar(128) NOT NULL,
      lead_count integer NOT NULL DEFAULT 0, success_count integer NOT NULL DEFAULT 0, failure_count integer NOT NULL DEFAULT 0, duplicate_count integer NOT NULL DEFAULT 0, unknown_count integer NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now(), approved_at timestamptz, started_at timestamptz, completed_at timestamptz, cancelled_at timestamptz, UNIQUE(tenant_id, idempotency_key)
    )""")
    op.execute("""CREATE TABLE vicidial_assignment_item (
      id uuid PRIMARY KEY, batch_id uuid NOT NULL REFERENCES vicidial_assignment_batch(id) ON DELETE RESTRICT, lead_record_id uuid NOT NULL REFERENCES lead_intelligence_record(id) ON DELETE RESTRICT,
      odoo_lead_id bigint NOT NULL, status varchar(32) NOT NULL DEFAULT 'ASSIGNMENT_QUEUED', vicidial_lead_id varchar(128), vicidial_list_id varchar(128) NOT NULL, vicidial_campaign_id varchar(128) NOT NULL,
      external_key varchar(255) NOT NULL UNIQUE, command_id uuid, attempt_count integer NOT NULL DEFAULT 0, error_class varchar(64), error_code varchar(64), safe_error_message varchar(512), created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, completed_at timestamptz
    )""")
    op.execute("""CREATE TABLE vicidial_assignment_attempt (
      id uuid PRIMARY KEY, assignment_item_id uuid NOT NULL REFERENCES vicidial_assignment_item(id) ON DELETE RESTRICT, attempt_number integer NOT NULL, request_hash char(64) NOT NULL,
      request_safe jsonb NOT NULL, response_safe jsonb, status varchar(32) NOT NULL, started_at timestamptz NOT NULL, completed_at timestamptz, duration_ms integer, error_class varchar(64), error_code varchar(64), safe_error_message varchar(512), UNIQUE(assignment_item_id, attempt_number)
    )""")
    op.execute("""CREATE TABLE vicidial_assignment_reconciliation (
      id uuid PRIMARY KEY, assignment_item_id uuid NOT NULL REFERENCES vicidial_assignment_item(id) ON DELETE RESTRICT, status varchar(24) NOT NULL DEFAULT 'PENDING', expected_external_key varchar(255) NOT NULL,
      observed_vicidial_lead_id varchar(128), result_safe jsonb NOT NULL, attempt_count integer NOT NULL DEFAULT 0, next_attempt_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_vicidial_assignment_batch_status ON vicidial_assignment_batch(tenant_id, status, created_at)")
    op.execute("CREATE INDEX ix_vicidial_assignment_item_status ON vicidial_assignment_item(batch_id, status)")


def downgrade() -> None:
    for table in ("vicidial_assignment_reconciliation", "vicidial_assignment_attempt", "vicidial_assignment_item", "vicidial_assignment_batch", "vicidial_assignment_policy"):
        op.drop_table(table)

