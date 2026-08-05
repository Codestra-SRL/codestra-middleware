"""Wave 3 durable Odoo business integration boundary.

Revision ID: 0035_odoo_business
Revises: 0034_wave2_event_governance
"""

from alembic import op

revision = "0035_odoo_business"
down_revision = "0034_wave2_event_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = (
        """
        CREATE TABLE odoo_business_command (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            public_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES iam_tenant(id),
            workspace_id uuid NOT NULL,
            resource_type varchar(64) NOT NULL,
            operation varchar(32) NOT NULL,
            resource_key varchar(128) NOT NULL,
            expected_version integer,
            payload jsonb NOT NULL,
            payload_hash varchar(71) NOT NULL,
            idempotency_key_hash varchar(64) NOT NULL,
            correlation_id varchar(128) NOT NULL,
            causation_id varchar(128),
            approval_state varchar(24) NOT NULL DEFAULT 'NOT_REQUIRED',
            approved_by varchar(128),
            approved_at timestamptz,
            state varchar(24) NOT NULL DEFAULT 'PENDING',
            delivery_mode varchar(16) NOT NULL DEFAULT 'DISABLED',
            attempt_count integer NOT NULL DEFAULT 0,
            max_attempts integer NOT NULL DEFAULT 5,
            next_attempt_at timestamptz NOT NULL DEFAULT now(),
            lease_owner varchar(128),
            lease_expires_at timestamptz,
            fencing_token bigint NOT NULL DEFAULT 0,
            cancel_requested_at timestamptz,
            last_error_code varchar(64),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            created_by varchar(128) NOT NULL,
            updated_by varchar(128) NOT NULL,
            version integer NOT NULL DEFAULT 1,
            audit_id uuid NOT NULL DEFAULT gen_random_uuid(),
            CONSTRAINT uq_odoo_business_command_idempotency
                UNIQUE (tenant_id, workspace_id, resource_type, idempotency_key_hash),
            CONSTRAINT fk_odoo_business_command_workspace
                FOREIGN KEY (tenant_id, workspace_id) REFERENCES iam_workspace(tenant_id, id),
            CONSTRAINT ck_odoo_business_resource_type CHECK (resource_type IN (
                'customer','company','contact','lead','crm_opportunity','activity',
                'appointment','project','task','support_ticket','call','callback',
                'recording','transcript','voice_ai_session','ai_employee',
                'marketplace_listing','commercial_record','subscription','usage_record',
                'sla','customer_health','document','knowledge_article','audit_record')),
            CONSTRAINT ck_odoo_business_operation CHECK (operation IN ('create','update','archive','link','transition')),
            CONSTRAINT ck_odoo_business_state CHECK (state IN ('PENDING','APPROVAL_REQUIRED','READY','LEASED','RETRY_WAIT','SUCCEEDED','FAILED','DEAD_LETTER','CANCELLED')),
            CONSTRAINT ck_odoo_business_approval CHECK (approval_state IN ('NOT_REQUIRED','PENDING','APPROVED','REJECTED')),
            CONSTRAINT ck_odoo_business_delivery_mode CHECK (delivery_mode IN ('DISABLED','MOCK','STAGING','PRODUCTION')),
            CONSTRAINT ck_odoo_business_attempts CHECK (attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10),
            CONSTRAINT ck_odoo_business_version CHECK (version >= 1),
            CONSTRAINT ck_odoo_business_payload_object CHECK (jsonb_typeof(payload) = 'object')
        )
        """,
        """
        CREATE TABLE odoo_business_reference (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES iam_tenant(id),
            workspace_id uuid NOT NULL,
            resource_type varchar(64) NOT NULL,
            resource_key varchar(128) NOT NULL,
            odoo_model varchar(96) NOT NULL,
            odoo_record_id bigint NOT NULL,
            remote_version varchar(128),
            remote_checksum varchar(71),
            status varchar(24) NOT NULL DEFAULT 'ACTIVE',
            last_reconciled_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            created_by varchar(128) NOT NULL,
            updated_by varchar(128) NOT NULL,
            version integer NOT NULL DEFAULT 1,
            audit_id uuid NOT NULL DEFAULT gen_random_uuid(),
            UNIQUE (tenant_id, workspace_id, resource_type, resource_key),
            UNIQUE (tenant_id, workspace_id, odoo_model, odoo_record_id),
            FOREIGN KEY (tenant_id, workspace_id) REFERENCES iam_workspace(tenant_id, id),
            CHECK (odoo_record_id > 0),
            CHECK (status IN ('ACTIVE','STALE','MISSING','CONFLICT','ARCHIVED')),
            CHECK (version >= 1)
        )
        """,
        """
        CREATE TABLE odoo_business_reconciliation (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES iam_tenant(id),
            workspace_id uuid NOT NULL,
            resource_type varchar(64) NOT NULL,
            resource_key varchar(128) NOT NULL,
            reference_id uuid REFERENCES odoo_business_reference(id),
            state varchar(24) NOT NULL DEFAULT 'PENDING',
            expected_checksum varchar(71),
            observed_checksum varchar(71),
            attempt_count integer NOT NULL DEFAULT 0,
            max_attempts integer NOT NULL DEFAULT 5,
            next_attempt_at timestamptz NOT NULL DEFAULT now(),
            lease_owner varchar(128),
            lease_expires_at timestamptz,
            fencing_token bigint NOT NULL DEFAULT 0,
            last_error_code varchar(64),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            created_by varchar(128) NOT NULL,
            updated_by varchar(128) NOT NULL,
            version integer NOT NULL DEFAULT 1,
            audit_id uuid NOT NULL DEFAULT gen_random_uuid(),
            UNIQUE (tenant_id, workspace_id, resource_type, resource_key, state),
            FOREIGN KEY (tenant_id, workspace_id) REFERENCES iam_workspace(tenant_id, id),
            CHECK (state IN ('PENDING','LEASED','RETRY_WAIT','MATCHED','DRIFT','MISSING','DEAD_LETTER')),
            CHECK (attempt_count >= 0 AND max_attempts BETWEEN 1 AND 10),
            CHECK (version >= 1)
        )
        """,
        """
        CREATE TABLE odoo_business_audit (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES iam_tenant(id),
            workspace_id uuid NOT NULL,
            command_id uuid REFERENCES odoo_business_command(id),
            reference_id uuid REFERENCES odoo_business_reference(id),
            reconciliation_id uuid REFERENCES odoo_business_reconciliation(id),
            action varchar(64) NOT NULL,
            actor varchar(128) NOT NULL,
            correlation_id varchar(128) NOT NULL,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (tenant_id, workspace_id) REFERENCES iam_workspace(tenant_id, id),
            CHECK (jsonb_typeof(metadata) = 'object')
        )
        """,
        "CREATE INDEX ix_odoo_command_claim ON odoo_business_command (state, next_attempt_at, created_at) WHERE state IN ('READY','RETRY_WAIT')",
        "CREATE INDEX ix_odoo_command_scope ON odoo_business_command (tenant_id, workspace_id, created_at DESC)",
        "CREATE INDEX ix_odoo_reference_scope ON odoo_business_reference (tenant_id, workspace_id, resource_type, resource_key)",
        "CREATE INDEX ix_odoo_reconcile_claim ON odoo_business_reconciliation (state, next_attempt_at) WHERE state IN ('PENDING','RETRY_WAIT')",
        "CREATE INDEX ix_odoo_audit_scope ON odoo_business_audit (tenant_id, workspace_id, created_at DESC)",
        """
        CREATE FUNCTION govern_odoo_business_row() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := now();
            NEW.updated_by := COALESCE(NEW.updated_by, OLD.updated_by);
            NEW.version := OLD.version + 1;
            RETURN NEW;
        END $$
        """,
        "CREATE TRIGGER odoo_command_govern BEFORE UPDATE ON odoo_business_command FOR EACH ROW EXECUTE FUNCTION govern_odoo_business_row()",
        "CREATE TRIGGER odoo_reference_govern BEFORE UPDATE ON odoo_business_reference FOR EACH ROW EXECUTE FUNCTION govern_odoo_business_row()",
        "CREATE TRIGGER odoo_reconciliation_govern BEFORE UPDATE ON odoo_business_reconciliation FOR EACH ROW EXECUTE FUNCTION govern_odoo_business_row()",
        """
        CREATE FUNCTION deny_odoo_business_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'append-only Odoo business audit'; END $$
        """,
        "CREATE TRIGGER odoo_business_audit_append_only BEFORE UPDATE OR DELETE ON odoo_business_audit FOR EACH ROW EXECUTE FUNCTION deny_odoo_business_audit_mutation()",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    for statement in (
        "DROP TRIGGER IF EXISTS odoo_business_audit_append_only ON odoo_business_audit",
        "DROP FUNCTION IF EXISTS deny_odoo_business_audit_mutation()",
        "DROP TRIGGER IF EXISTS odoo_reconciliation_govern ON odoo_business_reconciliation",
        "DROP TRIGGER IF EXISTS odoo_reference_govern ON odoo_business_reference",
        "DROP TRIGGER IF EXISTS odoo_command_govern ON odoo_business_command",
        "DROP FUNCTION IF EXISTS govern_odoo_business_row()",
        "DROP TABLE IF EXISTS odoo_business_audit",
        "DROP TABLE IF EXISTS odoo_business_reconciliation",
        "DROP TABLE IF EXISTS odoo_business_reference",
        "DROP TABLE IF EXISTS odoo_business_command",
    ):
        op.execute(statement)
