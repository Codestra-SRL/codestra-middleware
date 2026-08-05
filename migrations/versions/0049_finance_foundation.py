"""Loan and financial-services workflow foundation."""

from alembic import op

revision = "0049_finance_foundation"
down_revision = "0048_healthcare_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE finance_applicant (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, display_name varchar(255) NOT NULL,
      applicant_type varchar(32) NOT NULL DEFAULT 'APPLICANT', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE finance_application (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, applicant_id varchar(128) NOT NULL,
      status varchar(40) NOT NULL DEFAULT 'DRAFT', consent_status varchar(24) NOT NULL DEFAULT 'PENDING',
      disclosure_status varchar(24) NOT NULL DEFAULT 'PENDING', idempotency_key varchar(255) NOT NULL UNIQUE,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE finance_disclosure_acceptance (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, application_id varchar(128) NOT NULL,
      disclosure_code varchar(96) NOT NULL, version varchar(32) NOT NULL, accepted boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE finance_document (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, application_id varchar(128) NOT NULL,
      document_type varchar(64) NOT NULL, status varchar(32) NOT NULL DEFAULT 'REQUESTED',
      storage_reference varchar(255) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE finance_lender_product (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, lender_name varchar(255) NOT NULL,
      product_code varchar(96) NOT NULL, status varchar(24) NOT NULL DEFAULT 'ACTIVE',
      rule_version varchar(32) NOT NULL DEFAULT '1', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE finance_match_result (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, application_id varchar(128) NOT NULL,
      product_id varchar(128) NOT NULL, outcome varchar(40) NOT NULL, explanation_reference varchar(255) NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_finance_applicant_tenant ON finance_applicant(tenant_id)")
    op.execute("CREATE INDEX ix_finance_application_scope ON finance_application(tenant_id, status)")
    op.execute("CREATE INDEX ix_finance_disclosure_scope ON finance_disclosure_acceptance(tenant_id, application_id)")
    op.execute("CREATE INDEX ix_finance_document_scope ON finance_document(tenant_id, application_id, status)")
    op.execute("CREATE INDEX ix_finance_product_scope ON finance_lender_product(tenant_id, status)")
    op.execute("CREATE INDEX ix_finance_match_scope ON finance_match_result(tenant_id, application_id)")


def downgrade() -> None:
    for index, table in (
        ("ix_finance_match_scope", "finance_match_result"),
        ("ix_finance_product_scope", "finance_lender_product"),
        ("ix_finance_document_scope", "finance_document"),
        ("ix_finance_disclosure_scope", "finance_disclosure_acceptance"),
        ("ix_finance_application_scope", "finance_application"),
        ("ix_finance_applicant_tenant", "finance_applicant"),
    ):
        op.drop_index(index, table_name=table)
    for table in ("finance_match_result", "finance_lender_product", "finance_document", "finance_disclosure_acceptance", "finance_application", "finance_applicant"):
        op.drop_table(table)
