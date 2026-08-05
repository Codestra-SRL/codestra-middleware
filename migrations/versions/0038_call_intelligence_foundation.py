"""Call Intelligence jobs, protected recording references and QA records."""
from alembic import op

revision = "0038_call_intelligence_foundation"
down_revision = "0037_vicidial_campaign_canary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE call_intelligence_job (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128),
      vicidial_call_id varchar(128) NOT NULL, vicidial_uniqueid varchar(128) NOT NULL,
      odoo_lead_id bigint, campaign_id varchar(128), agent_user varchar(128),
      status varchar(32) NOT NULL DEFAULT 'CALL_COMPLETED', language varchar(16), duration_seconds integer,
      recording_reference_id uuid, transcript_id uuid, analysis_id uuid, qa_review_id uuid,
      idempotency_key varchar(255) NOT NULL, correlation_id varchar(128) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), started_at timestamptz, completed_at timestamptz,
      error_class varchar(64), error_code varchar(64), safe_error_message varchar(512),
      UNIQUE(tenant_id, idempotency_key), UNIQUE(tenant_id, vicidial_uniqueid)
    )""")
    op.execute("""CREATE TABLE call_recording_reference (
      id uuid PRIMARY KEY, call_job_id uuid NOT NULL UNIQUE REFERENCES call_intelligence_job(id) ON DELETE RESTRICT,
      provider varchar(64) NOT NULL, recording_id varchar(128) NOT NULL, storage_reference varchar(512) NOT NULL,
      format varchar(16) NOT NULL, duration_seconds integer, size_bytes bigint, checksum varchar(128),
      recorded_at timestamptz, retention_expires_at timestamptz, access_policy varchar(64) NOT NULL DEFAULT 'AUTHENTICATED_SHORT_LIVED',
      status varchar(24) NOT NULL DEFAULT 'AVAILABLE', created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE call_transcript (
      id uuid PRIMARY KEY, call_job_id uuid NOT NULL UNIQUE REFERENCES call_intelligence_job(id) ON DELETE RESTRICT,
      model_code varchar(128) NOT NULL, model_version varchar(128) NOT NULL, language varchar(16) NOT NULL,
      language_confidence double precision NOT NULL, speaker_count integer NOT NULL DEFAULT 0,
      transcript_text_encrypted_or_protected text NOT NULL, segments jsonb NOT NULL, redaction_status varchar(24) NOT NULL DEFAULT 'REDACTED',
      duration_ms integer, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE call_analysis (
      id uuid PRIMARY KEY, call_job_id uuid NOT NULL UNIQUE REFERENCES call_intelligence_job(id) ON DELETE RESTRICT,
      prompt_version varchar(128) NOT NULL, model_code varchar(128) NOT NULL, model_version varchar(128) NOT NULL,
      summary text NOT NULL, sentiment varchar(16) NOT NULL, disposition_recommendation varchar(128), objections jsonb NOT NULL,
      products_discussed jsonb NOT NULL, commitments jsonb NOT NULL, callback_recommendation jsonb NOT NULL,
      next_best_action text, compliance_findings jsonb NOT NULL, coaching_recommendations jsonb NOT NULL,
      confidence double precision NOT NULL, raw_result_safe jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE call_qa_score (
      id uuid PRIMARY KEY, call_job_id uuid NOT NULL UNIQUE REFERENCES call_intelligence_job(id) ON DELETE RESTRICT,
      scorecard_version varchar(64) NOT NULL, scores jsonb NOT NULL, overall_score double precision NOT NULL,
      severity varchar(32) NOT NULL, review_status varchar(24) NOT NULL DEFAULT 'REVIEW_REQUIRED', reviewed_by varchar(128), reviewed_at timestamptz,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE call_compliance_alert (
      id uuid PRIMARY KEY, call_job_id uuid NOT NULL REFERENCES call_intelligence_job(id) ON DELETE RESTRICT,
      alert_type varchar(64) NOT NULL, severity varchar(16) NOT NULL, evidence_reference varchar(512) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'OPEN', assigned_to varchar(128), resolved_by varchar(128), resolved_at timestamptz,
      resolution_notes text, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE call_intelligence_attempt (
      id uuid PRIMARY KEY, call_job_id uuid NOT NULL REFERENCES call_intelligence_job(id) ON DELETE RESTRICT,
      stage varchar(32) NOT NULL, attempt_number integer NOT NULL, service_code varchar(64) NOT NULL, status varchar(32) NOT NULL,
      started_at timestamptz NOT NULL, completed_at timestamptz, duration_ms integer, error_class varchar(64), error_code varchar(64), safe_error_message varchar(512),
      UNIQUE(call_job_id, stage, attempt_number)
    )""")
    op.execute("CREATE INDEX ix_call_intelligence_job_status ON call_intelligence_job(tenant_id, status, created_at)")
    op.execute("CREATE INDEX ix_call_compliance_alert_status ON call_compliance_alert(status, severity)")


def downgrade() -> None:
    for table in ("call_intelligence_attempt", "call_compliance_alert", "call_qa_score", "call_analysis", "call_transcript", "call_recording_reference", "call_intelligence_job"):
        op.drop_table(table)
