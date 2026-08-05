"""Healthcare transportation control-plane foundation."""

from alembic import op
import sqlalchemy as sa

revision = "0048_healthcare_foundation"
down_revision = "0047_voice_ai_governance_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE healthcare_patient (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, display_name varchar(255) NOT NULL,
      preferred_language varchar(32) NOT NULL DEFAULT '', data_classification varchar(24) NOT NULL DEFAULT 'PROTECTED',
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE healthcare_facility (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, name varchar(255) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'ACTIVE', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE healthcare_trip (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, patient_id varchar(128) NOT NULL,
      pickup_reference varchar(255) NOT NULL, destination_reference varchar(255) NOT NULL,
      service_level varchar(32) NOT NULL, status varchar(32) NOT NULL DEFAULT 'DRAFT',
      idempotency_key varchar(255) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE healthcare_claim (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, trip_id varchar(128) NOT NULL,
      status varchar(32) NOT NULL DEFAULT 'DRAFT', amount bigint NOT NULL DEFAULT 0,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.create_index("ix_healthcare_patient_tenant", "healthcare_patient", ["tenant_id"])
    op.create_index("ix_healthcare_facility_tenant", "healthcare_facility", ["tenant_id"])
    op.create_index("ix_healthcare_trip_tenant_status", "healthcare_trip", ["tenant_id", "status"])
    op.create_index("ix_healthcare_claim_tenant_status", "healthcare_claim", ["tenant_id", "status"])


def downgrade() -> None:
    for index, table in (
        ("ix_healthcare_claim_tenant_status", "healthcare_claim"),
        ("ix_healthcare_trip_tenant_status", "healthcare_trip"),
        ("ix_healthcare_facility_tenant", "healthcare_facility"),
        ("ix_healthcare_patient_tenant", "healthcare_patient"),
    ):
        op.drop_index(index, table_name=table)
    for table in ("healthcare_claim", "healthcare_trip", "healthcare_facility", "healthcare_patient"):
        op.drop_table(table)
