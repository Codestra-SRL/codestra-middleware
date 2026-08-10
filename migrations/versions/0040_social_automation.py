"""Social automation platform foundations.

Revision ID: 0040_social_automation
Revises: 0039_social_n8n_delivery
"""

from alembic import op

revision = "0040_social_automation"
down_revision = "0039_social_n8n_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        """CREATE TABLE platform_campaigns (
        id uuid PRIMARY KEY, tenant_id uuid NOT NULL, name varchar(255) NOT NULL,
        objective text NOT NULL, state varchar(32) NOT NULL DEFAULT 'DRAFT',
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_platform_campaign_state CHECK (state IN
        ('DRAFT','CONTENT_GENERATING','CONTENT_REVIEW','APPROVAL_REQUIRED','APPROVED',
        'SCHEDULED','ACTIVE','PAUSED','COMPLETED','FAILED','CANCELLED')))""",
        "CREATE INDEX ix_platform_campaign_tenant_state ON platform_campaigns(tenant_id,state,updated_at)",
        """CREATE TABLE campaign_state_transitions (
        id uuid PRIMARY KEY, campaign_id uuid NOT NULL REFERENCES platform_campaigns(id) ON DELETE RESTRICT,
        old_state varchar(32), new_state varchar(32) NOT NULL, reason varchar(1000) NOT NULL,
        actor varchar(255) NOT NULL, correlation_id varchar(255) NOT NULL,
        ai_model_reference varchar(255), approval_reference uuid,
        created_at timestamptz NOT NULL DEFAULT now())""",
        "CREATE INDEX ix_campaign_transition_campaign ON campaign_state_transitions(campaign_id,created_at)",
        """CREATE TABLE campaign_content_versions (
        id uuid PRIMARY KEY, campaign_id uuid NOT NULL REFERENCES platform_campaigns(id) ON DELETE RESTRICT,
        version integer NOT NULL, language varchar(16) NOT NULL, network varchar(32) NOT NULL,
        text_content text NOT NULL, media jsonb NOT NULL DEFAULT '[]'::jsonb, cta text,
        ai_generated boolean NOT NULL DEFAULT false, ai_model_reference varchar(255),
        risk_status varchar(32) NOT NULL, approval_status varchar(32) NOT NULL DEFAULT 'PENDING',
        approved_by varchar(255), approved_at timestamptz, created_by varchar(255) NOT NULL,
        correlation_id varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(campaign_id,network,language,version),
        CONSTRAINT ck_campaign_content_risk CHECK (risk_status IN ('PASS','REVIEW_REQUIRED','BLOCKED')),
        CONSTRAINT ck_campaign_content_approval CHECK (approval_status IN ('PENDING','APPROVED','REJECTED')))""",
        """CREATE TABLE campaign_approvals (
        id uuid PRIMARY KEY, content_id uuid NOT NULL REFERENCES campaign_content_versions(id) ON DELETE RESTRICT,
        content_version integer NOT NULL, actor varchar(255) NOT NULL,
        decision varchar(16) NOT NULL, reason varchar(1000) NOT NULL,
        correlation_id varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT ck_campaign_approval_decision CHECK (decision IN ('APPROVED','REJECTED')))""",
        """CREATE TABLE lead_intelligence_results (
        id uuid PRIMARY KEY, tenant_id uuid NOT NULL, campaign_id uuid,
        source_event_id varchar(255) NOT NULL, category varchar(32) NOT NULL,
        quality_score integer NOT NULL, factor_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
        identity_hash char(64), consent_status varchar(32) NOT NULL DEFAULT 'UNKNOWN',
        dnc_status varchar(32) NOT NULL DEFAULT 'UNKNOWN', result_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
        correlation_id varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
        UNIQUE(tenant_id,source_event_id), CHECK(quality_score BETWEEN 0 AND 100))""",
        "CREATE INDEX ix_lead_intelligence_identity ON lead_intelligence_results(tenant_id,identity_hash)",
        """CREATE TABLE provider_health_snapshots (
        id uuid PRIMARY KEY, provider varchar(32) NOT NULL, account_id uuid,
        score integer NOT NULL, status varchar(32) NOT NULL, components jsonb NOT NULL,
        correlation_id varchar(255) NOT NULL, observed_at timestamptz NOT NULL DEFAULT now(),
        CHECK(score BETWEEN 0 AND 100))""",
        "CREATE INDEX ix_provider_health_recent ON provider_health_snapshots(provider,observed_at)",
        """CREATE TABLE workflow_deployment_states (
        id uuid PRIMARY KEY, workflow_name varchar(255) NOT NULL, workflow_version varchar(64) NOT NULL,
        git_sha char(40) NOT NULL, environment varchar(16) NOT NULL, deployed_by varchar(255) NOT NULL,
        previous_version varchar(64), result varchar(32) NOT NULL, rollback_pointer varchar(255) NOT NULL,
        deployed_at timestamptz NOT NULL DEFAULT now(), UNIQUE(workflow_name,environment,workflow_version))""",
        """CREATE TABLE workflow_security_audits (
        id uuid PRIMARY KEY, environment varchar(16) NOT NULL, workflow_name varchar(255),
        severity varchar(16) NOT NULL, finding_code varchar(64) NOT NULL, safe_summary varchar(1000) NOT NULL,
        git_sha char(40), created_at timestamptz NOT NULL DEFAULT now(),
        CHECK(severity IN ('INFO','LOW','MEDIUM','HIGH','CRITICAL')))""",
        """CREATE TABLE workflow_drift_events (
        id uuid PRIMARY KEY, workflow_name varchar(255) NOT NULL, environment varchar(16) NOT NULL,
        expected_hash char(64) NOT NULL, observed_hash char(64) NOT NULL, status varchar(32) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE platform_media_assets (
        id uuid PRIMARY KEY, tenant_id uuid NOT NULL, content_type varchar(128) NOT NULL,
        size_bytes bigint NOT NULL, checksum char(64) NOT NULL, storage_backend varchar(32) NOT NULL,
        location_reference varchar(1000) NOT NULL, status varchar(32) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz,
        UNIQUE(tenant_id,checksum), CHECK(size_bytes > 0))""",
        """CREATE TABLE social_ops_incidents (
        id uuid PRIMARY KEY, severity varchar(16) NOT NULL, incident_type varchar(64) NOT NULL,
        provider varchar(32), campaign_id uuid, status varchar(32) NOT NULL DEFAULT 'OPEN',
        safe_summary varchar(1000) NOT NULL, correlation_id varchar(255) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz)""",
        """CREATE TABLE platform_trace_links (
        id uuid PRIMARY KEY, trace_id varchar(64) NOT NULL, correlation_id varchar(255) NOT NULL,
        request_id varchar(255), event_id varchar(255), delivery_id uuid,
        workflow_execution_id varchar(255), subject_type varchar(64) NOT NULL,
        subject_id varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""",
        "CREATE INDEX ix_platform_trace_correlation ON platform_trace_links(correlation_id,created_at)",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    for statement in (
        "DROP INDEX ix_platform_trace_correlation",
        "DROP TABLE platform_trace_links",
        "DROP TABLE social_ops_incidents",
        "DROP TABLE platform_media_assets",
        "DROP TABLE workflow_drift_events",
        "DROP TABLE workflow_security_audits",
        "DROP TABLE workflow_deployment_states",
        "DROP INDEX ix_provider_health_recent",
        "DROP TABLE provider_health_snapshots",
        "DROP INDEX ix_lead_intelligence_identity",
        "DROP TABLE lead_intelligence_results",
        "DROP TABLE campaign_approvals",
        "DROP TABLE campaign_content_versions",
        "DROP INDEX ix_campaign_transition_campaign",
        "DROP TABLE campaign_state_transitions",
        "DROP INDEX ix_platform_campaign_tenant_state",
        "DROP TABLE platform_campaigns",
    ):
        op.execute(statement)
