"""Legal intake and matter-management foundation."""

from alembic import op

revision = "0050_legal_foundation"
down_revision = "0049_finance_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE legal_prospect (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, display_name varchar(255) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE legal_intake (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, prospect_id varchar(128) NOT NULL,
      status varchar(40) NOT NULL DEFAULT 'DRAFT', idempotency_key varchar(255) NOT NULL UNIQUE,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE legal_matter (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, client_id varchar(128) NOT NULL,
      name varchar(255) NOT NULL, status varchar(32) NOT NULL DEFAULT 'DRAFT',
      confidentiality_level varchar(24) NOT NULL DEFAULT 'CONFIDENTIAL', idempotency_key varchar(255) NOT NULL UNIQUE,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE legal_conflict_request (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, intake_id varchar(128) NOT NULL,
      outcome varchar(40) NOT NULL DEFAULT 'INSUFFICIENT_INFORMATION', reviewer_id varchar(128) NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE legal_document (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, matter_id varchar(128) NOT NULL,
      category varchar(64) NOT NULL, privilege_classification varchar(32) NOT NULL DEFAULT 'CONFIDENTIAL',
      status varchar(32) NOT NULL DEFAULT 'UPLOADED', storage_reference varchar(255) NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE legal_engagement (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, matter_id varchar(128) NOT NULL,
      status varchar(32) NOT NULL DEFAULT 'DRAFT', version bigint NOT NULL DEFAULT 1,
      client_signed boolean NOT NULL DEFAULT false, firm_signed boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for index, table, columns in (
        ("ix_legal_prospect_tenant", "legal_prospect", "tenant_id"),
        ("ix_legal_intake_scope", "legal_intake", "tenant_id,status"),
        ("ix_legal_matter_scope", "legal_matter", "tenant_id,status"),
        ("ix_legal_conflict_scope", "legal_conflict_request", "tenant_id,intake_id"),
        ("ix_legal_document_scope", "legal_document", "tenant_id,matter_id,status"),
        ("ix_legal_engagement_scope", "legal_engagement", "tenant_id,matter_id"),
    ):
        op.execute(f"CREATE INDEX {index} ON {table} ({columns})")


def downgrade() -> None:
    for index, table in (
        ("ix_legal_engagement_scope", "legal_engagement"),
        ("ix_legal_document_scope", "legal_document"),
        ("ix_legal_conflict_scope", "legal_conflict_request"),
        ("ix_legal_matter_scope", "legal_matter"),
        ("ix_legal_intake_scope", "legal_intake"),
        ("ix_legal_prospect_tenant", "legal_prospect"),
    ):
        op.drop_index(index, table_name=table)
    for table in ("legal_engagement", "legal_document", "legal_conflict_request", "legal_matter", "legal_intake", "legal_prospect"):
        op.drop_table(table)
