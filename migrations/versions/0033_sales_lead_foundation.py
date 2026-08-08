"""Add governed, dry-run sales lead foundation records.

Revision ID: 0033_sales_lead_foundation
Revises: 0032_ai_worker_queue_runtime
"""

from alembic import op

revision = "0033_sales_lead_foundation"
down_revision = "0032_ai_worker_queue_runtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        """CREATE TABLE sales_lead_candidates (
          id uuid PRIMARY KEY, tenant_id text NOT NULL, campaign_id text NOT NULL,
          schema_version text NOT NULL, protected_payload_hash char(64) NOT NULL,
          source_provider text NOT NULL, source_request_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, source_provider, source_request_id),
          CHECK (schema_version='codestra.sales.lead-candidate.v1'),
          CHECK (protected_payload_hash ~ '^[0-9a-f]{64}$'))""",
        """CREATE TABLE sales_duplicate_reviews (
          id uuid PRIMARY KEY, candidate_id uuid NOT NULL REFERENCES sales_lead_candidates(id),
          tenant_id text NOT NULL, campaign_id text NOT NULL, odoo_company_id text,
          odoo_lead_id text, company_score integer NOT NULL, contact_score integer NOT NULL,
          reason_codes jsonb NOT NULL, evidence_references jsonb NOT NULL,
          policy_version text NOT NULL, review_state text NOT NULL DEFAULT 'PENDING',
          reviewer_identity text, reviewed_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (company_score BETWEEN 0 AND 100), CHECK (contact_score BETWEEN 0 AND 100))""",
        """CREATE TABLE sales_verification_jobs (
          id uuid PRIMARY KEY, tenant_id text NOT NULL, campaign_id text,
          state text NOT NULL, dry_run boolean NOT NULL DEFAULT true,
          write_changes boolean NOT NULL DEFAULT false,
          publish_to_vicidial boolean NOT NULL DEFAULT false,
          batch_size integer NOT NULL, total_count integer NOT NULL DEFAULT 0,
          processed_count integer NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now(),
          completed_at timestamptz,
          CHECK (dry_run AND NOT write_changes AND NOT publish_to_vicidial),
          CHECK (batch_size BETWEEN 1 AND 100))""",
        """CREATE TABLE sales_verification_results (
          id uuid PRIMARY KEY, job_id uuid NOT NULL REFERENCES sales_verification_jobs(id),
          tenant_id text NOT NULL, odoo_lead_id text NOT NULL, classification text NOT NULL,
          reason_codes jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE(job_id,odoo_lead_id))""",
        """CREATE TABLE sales_idempotency_records (
          id uuid PRIMARY KEY, tenant_id text NOT NULL, operation text NOT NULL,
          key_hash char(64) NOT NULL, payload_hash char(64) NOT NULL,
          result_reference text, status text NOT NULL, correlation_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
          UNIQUE(tenant_id,operation,key_hash),
          CHECK (key_hash ~ '^[0-9a-f]{64}$'), CHECK (payload_hash ~ '^[0-9a-f]{64}$'))""",
        """CREATE TABLE sales_webhook_nonces (
          id uuid PRIMARY KEY, scraper_identity text NOT NULL, tenant_id text NOT NULL,
          nonce_hash char(64) NOT NULL, request_id text NOT NULL,
          payload_hash char(64) NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL, UNIQUE(scraper_identity,nonce_hash))""",
        """CREATE TABLE sales_audit_events (
          id uuid PRIMARY KEY, event_type text NOT NULL, tenant_id text NOT NULL,
          actor_identity text NOT NULL, correlation_id text NOT NULL,
          candidate_or_job_id text, decision text, reason_codes jsonb NOT NULL,
          policy_version text NOT NULL, protected_payload_hash char(64) NOT NULL,
          source_provider text NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE FUNCTION deny_sales_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN RAISE EXCEPTION 'append-only sales audit evidence'; END $$""",
        """CREATE TRIGGER sales_audit_append_only BEFORE UPDATE OR DELETE ON sales_audit_events
          FOR EACH ROW EXECUTE FUNCTION deny_sales_audit_mutation()""",
        "CREATE INDEX ix_sales_candidate_tenant_campaign ON sales_lead_candidates(tenant_id,campaign_id,created_at DESC)",
        "CREATE INDEX ix_sales_review_tenant_state ON sales_duplicate_reviews(tenant_id,review_state,created_at DESC)",
        "CREATE INDEX ix_sales_jobs_tenant_state ON sales_verification_jobs(tenant_id,state,created_at DESC)",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    for statement in (
        "DROP INDEX ix_sales_jobs_tenant_state",
        "DROP INDEX ix_sales_review_tenant_state",
        "DROP INDEX ix_sales_candidate_tenant_campaign",
        "DROP TRIGGER sales_audit_append_only ON sales_audit_events",
        "DROP FUNCTION deny_sales_audit_mutation()",
        "DROP TABLE sales_audit_events",
        "DROP TABLE sales_webhook_nonces",
        "DROP TABLE sales_idempotency_records",
        "DROP TABLE sales_verification_results",
        "DROP TABLE sales_verification_jobs",
        "DROP TABLE sales_duplicate_reviews",
        "DROP TABLE sales_lead_candidates",
    ):
        op.execute(statement)
