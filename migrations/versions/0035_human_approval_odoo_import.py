"""Human lead review and controlled Odoo import state."""

from alembic import op

revision = "0035_human_approval_odoo_import"
down_revision = "0034_qwen_staging_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE lead_review (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128),
      lead_record_id uuid NOT NULL REFERENCES lead_intelligence_record(id) ON DELETE RESTRICT,
      status varchar(32) NOT NULL DEFAULT 'REVIEW_REQUIRED', assigned_reviewer_id varchar(128),
      review_policy_id uuid, review_priority integer NOT NULL DEFAULT 5, review_notes text,
      decision varchar(32), decision_reason varchar(1024), decision_by varchar(128), decision_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(tenant_id, lead_record_id), CHECK(review_priority BETWEEN 0 AND 9)
    )""")
    op.execute("""CREATE TABLE lead_review_event (
      id uuid PRIMARY KEY, lead_review_id uuid NOT NULL REFERENCES lead_review(id) ON DELETE RESTRICT,
      event_type varchar(64) NOT NULL, actor_id varchar(128) NOT NULL, actor_type varchar(32) NOT NULL,
      payload_safe jsonb NOT NULL, correlation_id varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE lead_approval_policy (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128), policy_code varchar(96) NOT NULL,
      version integer NOT NULL, configuration jsonb NOT NULL, status varchar(24) NOT NULL DEFAULT 'TESTING',
      approved_by varchar(128), approved_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(tenant_id, workspace_id, policy_code, version)
    )""")
    op.execute("""CREATE TABLE odoo_import_batch (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128), batch_code varchar(128) NOT NULL UNIQUE,
      status varchar(32) NOT NULL DEFAULT 'REQUESTED', requested_by varchar(128) NOT NULL, approved_by varchar(128),
      idempotency_key varchar(255) NOT NULL, correlation_id varchar(128) NOT NULL, lead_count integer NOT NULL DEFAULT 0,
      success_count integer NOT NULL DEFAULT 0, failure_count integer NOT NULL DEFAULT 0, unknown_count integer NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now(), approved_at timestamptz, started_at timestamptz, completed_at timestamptz, cancelled_at timestamptz,
      UNIQUE(tenant_id, idempotency_key)
    )""")
    op.execute("""CREATE TABLE odoo_import_item (
      id uuid PRIMARY KEY, batch_id uuid NOT NULL REFERENCES odoo_import_batch(id) ON DELETE RESTRICT,
      lead_record_id uuid NOT NULL REFERENCES lead_intelligence_record(id) ON DELETE RESTRICT, status varchar(32) NOT NULL DEFAULT 'QUEUED',
      odoo_model varchar(64) NOT NULL DEFAULT 'crm.lead', odoo_record_id bigint, odoo_external_key varchar(255) NOT NULL UNIQUE,
      command_id uuid, attempt_count integer NOT NULL DEFAULT 0, error_class varchar(64), error_code varchar(64), safe_error_message varchar(512),
      created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, completed_at timestamptz
    )""")
    op.execute("""CREATE TABLE odoo_import_attempt (
      id uuid PRIMARY KEY, import_item_id uuid NOT NULL REFERENCES odoo_import_item(id) ON DELETE RESTRICT, attempt_number integer NOT NULL,
      request_hash char(64) NOT NULL, request_safe jsonb NOT NULL, response_safe jsonb, status varchar(32) NOT NULL,
      started_at timestamptz NOT NULL, completed_at timestamptz, duration_ms integer, error_class varchar(64), error_code varchar(64), safe_error_message varchar(512),
      UNIQUE(import_item_id, attempt_number)
    )""")
    op.execute("""CREATE TABLE odoo_import_reconciliation (
      id uuid PRIMARY KEY, import_item_id uuid NOT NULL REFERENCES odoo_import_item(id) ON DELETE RESTRICT, status varchar(24) NOT NULL DEFAULT 'PENDING',
      reconciliation_type varchar(64) NOT NULL, expected_external_key varchar(255) NOT NULL, observed_odoo_record_id bigint,
      result_safe jsonb NOT NULL, attempt_count integer NOT NULL DEFAULT 0, next_attempt_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_lead_review_queue ON lead_review(tenant_id, status, review_priority)")
    op.execute("CREATE INDEX ix_odoo_import_item_batch_status ON odoo_import_item(batch_id, status)")
    op.execute("CREATE INDEX ix_odoo_import_reconciliation_status ON odoo_import_reconciliation(status, next_attempt_at)")


def downgrade() -> None:
    for table in ("odoo_import_reconciliation", "odoo_import_attempt", "odoo_import_item", "odoo_import_batch", "lead_approval_policy", "lead_review_event", "lead_review"):
        op.drop_table(table)

