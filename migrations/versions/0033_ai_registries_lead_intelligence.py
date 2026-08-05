"""AI registries, approvals, lead intelligence and reconciliation foundation.

Revision ID: 0033_ai_registries_lead_intelligence
Revises: 0032_ai_platform_foundation
"""

from alembic import op

revision = "0033_ai_registries_lead_intelligence"
down_revision = "0032_ai_platform_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE ai_prompt (
      id uuid PRIMARY KEY, service_code varchar(64) NOT NULL,
      task_code varchar(96) NOT NULL, name varchar(128) NOT NULL,
      description varchar(512), created_by varchar(128) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_prompt_version (
      id uuid PRIMARY KEY, prompt_id uuid NOT NULL REFERENCES ai_prompt(id) ON DELETE RESTRICT,
      version integer NOT NULL, system_prompt text NOT NULL, developer_prompt text,
      output_schema jsonb NOT NULL, status varchar(24) NOT NULL DEFAULT 'DRAFT',
      approved_by varchar(128), approved_at timestamptz, created_by varchar(128) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(prompt_id, version), CHECK(version >= 1),
      CHECK(status IN ('DRAFT','TESTING','REVIEW','APPROVED','ACTIVE','DEPRECATED','RETIRED'))
    )""")
    op.execute("""CREATE TABLE ai_model (
      id uuid PRIMARY KEY, model_code varchar(96) NOT NULL UNIQUE,
      display_name varchar(128) NOT NULL, provider varchar(64) NOT NULL,
      endpoint_reference varchar(255) NOT NULL, capabilities jsonb NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'DISABLED', health_status varchar(24),
      fallback_model_id uuid, created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_model_policy (
      id uuid PRIMARY KEY, policy_code varchar(96) NOT NULL UNIQUE,
      description varchar(512), primary_model_id uuid, fallback_model_id uuid,
      timeout_seconds integer NOT NULL DEFAULT 30, maximum_attempts integer NOT NULL DEFAULT 3,
      maximum_input_size integer NOT NULL DEFAULT 65536, maximum_output_size integer NOT NULL DEFAULT 65536,
      allowed_data_classifications jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK(timeout_seconds > 0), CHECK(maximum_attempts > 0)
    )""")
    op.execute("""CREATE TABLE ai_approval (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128),
      ai_job_id uuid REFERENCES ai_job(id) ON DELETE RESTRICT, action_type varchar(96) NOT NULL,
      action_payload jsonb NOT NULL, status varchar(24) NOT NULL DEFAULT 'PENDING',
      requested_by varchar(128), reviewed_by varchar(128), review_comment varchar(1024),
      expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), reviewed_at timestamptz,
      CHECK(status IN ('PENDING','APPROVED','REJECTED','EXPIRED'))
    )""")
    op.execute("""CREATE TABLE ai_output_schema (
      id uuid PRIMARY KEY, schema_code varchar(96) NOT NULL, schema_version integer NOT NULL,
      service_code varchar(64) NOT NULL, task_code varchar(96) NOT NULL,
      json_schema jsonb NOT NULL, status varchar(24) NOT NULL DEFAULT 'DRAFT',
      approved_by varchar(128), approved_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(schema_code, schema_version), CHECK(schema_version >= 1)
    )""")
    op.execute("""CREATE TABLE lead_search (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128),
      ai_job_id uuid NOT NULL UNIQUE REFERENCES ai_job(id) ON DELETE RESTRICT,
      industry varchar(128), keywords jsonb NOT NULL, location_payload jsonb NOT NULL,
      requirements_payload jsonb NOT NULL, maximum_results integer NOT NULL DEFAULT 100,
      minimum_confidence numeric(5,4) NOT NULL DEFAULT 0.7500, target_odoo_team varchar(128),
      status varchar(32) NOT NULL DEFAULT 'QUEUED', created_by varchar(128),
      created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, completed_at timestamptz,
      CHECK(maximum_results BETWEEN 1 AND 10000), CHECK(minimum_confidence BETWEEN 0 AND 1)
    )""")
    op.execute("""CREATE TABLE lead_intelligence_record (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128),
      search_id uuid NOT NULL REFERENCES lead_search(id) ON DELETE RESTRICT,
      company_name varchar(255) NOT NULL, normalized_company_name varchar(255) NOT NULL,
      website varchar(2048), normalized_domain varchar(255), phone varchar(64),
      normalized_phone varchar(64), email varchar(320), normalized_email varchar(320),
      address_payload jsonb, social_profiles jsonb, contacts jsonb,
      ownership_status varchar(32) NOT NULL DEFAULT 'UNKNOWN', ownership_confidence numeric(5,4) NOT NULL DEFAULT 0,
      ownership_source varchar(2048), verification_status varchar(32) NOT NULL DEFAULT 'UNVERIFIED',
      lead_score numeric(5,2) NOT NULL DEFAULT 0, duplicate_status varchar(32) NOT NULL DEFAULT 'UNREVIEWED',
      duplicate_of_record_id uuid, source_history jsonb NOT NULL, odoo_lead_id bigint,
      status varchar(32) NOT NULL DEFAULT 'DISCOVERED', created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      CHECK(ownership_confidence BETWEEN 0 AND 1), CHECK(lead_score BETWEEN 0 AND 100)
    )""")
    op.execute("""CREATE TABLE ai_reconciliation (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, resource_type varchar(64) NOT NULL,
      resource_id varchar(128) NOT NULL, status varchar(24) NOT NULL DEFAULT 'DRY_RUN',
      observed_payload jsonb NOT NULL, discrepancy_code varchar(64),
      created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz
    )""")
    op.execute("CREATE INDEX ix_ai_approval_scope ON ai_approval(tenant_id, workspace_id, status)")
    op.execute("CREATE INDEX ix_lead_record_identity ON lead_intelligence_record(tenant_id, normalized_domain, normalized_email, normalized_phone)")
    op.execute("CREATE INDEX ix_ai_reconciliation_status ON ai_reconciliation(status, created_at)")


def downgrade() -> None:
    op.drop_table("ai_reconciliation")
    op.drop_table("lead_intelligence_record")
    op.drop_table("lead_search")
    op.drop_table("ai_output_schema")
    op.drop_table("ai_approval")
    op.drop_table("ai_model_policy")
    op.drop_table("ai_model")
    op.drop_table("ai_prompt_version")
    op.drop_table("ai_prompt")
