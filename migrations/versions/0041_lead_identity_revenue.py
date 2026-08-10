"""Lead identity graph, next-action, and revenue attribution.

Revision ID: 0041_lead_identity_revenue
Revises: 0040_social_automation, 0034_sales_lead_foundation
"""

from alembic import op

revision = "0041_lead_identity_revenue"
down_revision = ("0040_social_automation", "0034_sales_lead_foundation")
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        """CREATE TABLE person_identities (id uuid PRIMARY KEY, tenant_id uuid NOT NULL,
        display_name varchar(255), first_name varchar(128), last_name varchar(128), preferred_language varchar(16),
        country varchar(2), timezone varchar(64), status varchar(32) NOT NULL DEFAULT 'ACTIVE', merged_into_id uuid REFERENCES person_identities(id),
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""",
        "CREATE INDEX ix_person_identity_tenant ON person_identities(tenant_id,status)",
        """CREATE TABLE company_identities (id uuid PRIMARY KEY, tenant_id uuid NOT NULL,
        legal_name varchar(255), display_name varchar(255), domain varchar(255), country varchar(2), industry varchar(255),
        registration_number varchar(128), status varchar(32) NOT NULL DEFAULT 'ACTIVE', merged_into_id uuid REFERENCES company_identities(id),
        provenance jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""",
        "CREATE UNIQUE INDEX uq_company_tenant_domain ON company_identities(tenant_id,domain) WHERE domain IS NOT NULL AND merged_into_id IS NULL",
        """CREATE TABLE identity_aliases (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, person_id uuid REFERENCES person_identities(id), company_id uuid REFERENCES company_identities(id),
        alias_type varchar(32) NOT NULL, normalized_value varchar(512) NOT NULL, display_value varchar(512), source varchar(64) NOT NULL,
        first_seen_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
        CHECK ((person_id IS NOT NULL) <> (company_id IS NOT NULL)), UNIQUE(tenant_id,alias_type,normalized_value))""",
        """CREATE TABLE contact_points (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, person_id uuid REFERENCES person_identities(id), company_id uuid REFERENCES company_identities(id),
        type varchar(16) NOT NULL, normalized_hash char(64) NOT NULL, normalized_value_encrypted text, display_masked varchar(128) NOT NULL,
        normalization_status varchar(32) NOT NULL, verification_state varchar(32) NOT NULL DEFAULT 'UNKNOWN', source varchar(64) NOT NULL,
        first_seen_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(), is_primary boolean NOT NULL DEFAULT false,
        metadata jsonb NOT NULL DEFAULT '{}'::jsonb, CHECK ((person_id IS NOT NULL) <> (company_id IS NOT NULL)),
        UNIQUE(tenant_id,type,normalized_hash))""",
        """CREATE TABLE social_identities (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, provider varchar(32) NOT NULL, network varchar(32) NOT NULL,
        provider_profile_id varchar(255) NOT NULL, profile_handle varchar(255), profile_reference varchar(1000), person_id uuid REFERENCES person_identities(id), company_id uuid REFERENCES company_identities(id),
        first_seen_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(),
        CHECK ((person_id IS NOT NULL) <> (company_id IS NOT NULL)), UNIQUE(tenant_id,provider,network,provider_profile_id))""",
        """CREATE TABLE external_system_identities (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, system varchar(64) NOT NULL, entity_type varchar(64) NOT NULL,
        external_id_hash char(64) NOT NULL, safe_reference varchar(255) NOT NULL, person_id uuid REFERENCES person_identities(id), company_id uuid REFERENCES company_identities(id),
        created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,system,entity_type,external_id_hash))""",
        """CREATE TABLE identity_links (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, source_type varchar(32) NOT NULL, source_id uuid NOT NULL,
        target_type varchar(32) NOT NULL, target_id uuid NOT NULL, confidence varchar(16) NOT NULL, score integer NOT NULL,
        evidence jsonb NOT NULL, status varchar(32) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), CHECK(score BETWEEN 0 AND 100))""",
        """CREATE TABLE identity_resolution_attempts (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, request_hash char(64) NOT NULL,
        result_identity_id uuid, confidence varchar(16) NOT NULL, score integer NOT NULL, signal_summary jsonb NOT NULL,
        conflict boolean NOT NULL DEFAULT false, correlation_id varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE identity_merge_decisions (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, entity_type varchar(32) NOT NULL,
        source_id uuid NOT NULL, target_id uuid NOT NULL, actor varchar(255) NOT NULL, action varchar(16) NOT NULL,
        confidence varchar(16) NOT NULL, evidence jsonb NOT NULL, reason varchar(1000) NOT NULL, correlation_id varchar(255) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE lead_records (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, person_id uuid REFERENCES person_identities(id), company_id uuid REFERENCES company_identities(id),
        source varchar(64) NOT NULL, status varchar(32) NOT NULL DEFAULT 'NEW', campaign_id uuid, content_id uuid,
        consent_status varchar(32) NOT NULL DEFAULT 'UNKNOWN', dnc_status varchar(32) NOT NULL DEFAULT 'UNKNOWN', jurisdiction varchar(32),
        owner_reference varchar(255), current_score integer NOT NULL DEFAULT 0, next_best_action varchar(32) NOT NULL DEFAULT 'NO_ACTION', metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), CHECK(current_score BETWEEN 0 AND 100))""",
        "CREATE INDEX ix_lead_identity_campaign ON lead_records(tenant_id,person_id,company_id,campaign_id,status)",
        """CREATE TABLE lead_interactions (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, lead_id uuid NOT NULL REFERENCES lead_records(id) ON DELETE RESTRICT,
        interaction_type varchar(32) NOT NULL, source varchar(64) NOT NULL, source_event_id varchar(255) NOT NULL,
        campaign_id uuid, content_id uuid, correlation_id varchar(255) NOT NULL, external_reference varchar(255), safe_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
        occurred_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,source,source_event_id))""",
        """CREATE TABLE lead_consents (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, person_id uuid REFERENCES person_identities(id), company_id uuid REFERENCES company_identities(id),
        channel varchar(32) NOT NULL, status varchar(16) NOT NULL, source varchar(64) NOT NULL, collected_at timestamptz, expires_at timestamptz,
        jurisdiction varchar(32), evidence_reference varchar(255), revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE lead_dnc_statuses (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, person_id uuid REFERENCES person_identities(id), company_id uuid REFERENCES company_identities(id),
        channel varchar(32), status varchar(32) NOT NULL, source varchar(64) NOT NULL, evidence_reference varchar(255),
        effective_at timestamptz NOT NULL, expires_at timestamptz, created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE next_action_decisions (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, lead_id uuid NOT NULL REFERENCES lead_records(id) ON DELETE RESTRICT,
        action varchar(32) NOT NULL, eligible_for_contact boolean NOT NULL, reasons jsonb NOT NULL, rule_version varchar(32) NOT NULL,
        actor varchar(255) NOT NULL, correlation_id varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE action_feedback (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, lead_id uuid NOT NULL REFERENCES lead_records(id) ON DELETE RESTRICT,
        decision_id uuid NOT NULL REFERENCES next_action_decisions(id) ON DELETE RESTRICT, outcome varchar(32) NOT NULL,
        safe_metadata jsonb NOT NULL DEFAULT '{}'::jsonb, actor varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""",
        """CREATE TABLE lead_campaign_touches (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, lead_id uuid NOT NULL REFERENCES lead_records(id) ON DELETE RESTRICT,
        identity_id uuid, campaign_id uuid NOT NULL, content_id uuid, network varchar(32), provider varchar(32), source varchar(64) NOT NULL,
        utm jsonb NOT NULL DEFAULT '{}'::jsonb, event_type varchar(64) NOT NULL, source_event_id varchar(255) NOT NULL,
        occurred_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,source,source_event_id))""",
        """CREATE TABLE revenue_events (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, identity_id uuid, lead_id uuid REFERENCES lead_records(id),
        opportunity_reference varchar(255), campaign_reference uuid, amount numeric(20,6), currency char(3), type varchar(32) NOT NULL,
        occurred_at timestamptz NOT NULL, source_system varchar(64) NOT NULL, external_reference_hash char(64) NOT NULL,
        confidence varchar(16) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,source_system,external_reference_hash),
        CHECK ((amount IS NULL AND currency IS NULL) OR (amount IS NOT NULL AND currency IS NOT NULL)))""",
        """CREATE TABLE attribution_calculations (id uuid PRIMARY KEY, revenue_event_id uuid NOT NULL REFERENCES revenue_events(id) ON DELETE RESTRICT,
        version integer NOT NULL, model varchar(32) NOT NULL, settings jsonb NOT NULL, superseded boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(revenue_event_id,version,model))""",
        """CREATE TABLE attribution_allocations (id uuid PRIMARY KEY, calculation_id uuid NOT NULL REFERENCES attribution_calculations(id) ON DELETE RESTRICT,
        touch_id uuid NOT NULL REFERENCES lead_campaign_touches(id) ON DELETE RESTRICT, campaign_id uuid NOT NULL, content_id uuid,
        weight numeric(18,15) NOT NULL, attributed_amount numeric(20,6), currency char(3), created_at timestamptz NOT NULL DEFAULT now(),
        CHECK(weight >= 0 AND weight <= 1))""",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    for table in (
        "attribution_allocations",
        "attribution_calculations",
        "revenue_events",
        "lead_campaign_touches",
        "action_feedback",
        "next_action_decisions",
        "lead_dnc_statuses",
        "lead_consents",
        "lead_interactions",
        "lead_records",
        "identity_merge_decisions",
        "identity_resolution_attempts",
        "identity_links",
        "external_system_identities",
        "social_identities",
        "contact_points",
        "identity_aliases",
        "company_identities",
        "person_identities",
    ):
        op.execute(f"DROP TABLE {table}")
