"""Operations inventory, incidents, readiness gates and backup verification."""
from alembic import op

revision = "0039_operations_reliability"
down_revision = "0038_call_intelligence_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE service_inventory (
      service_code varchar(96) PRIMARY KEY, display_name varchar(160) NOT NULL, server_ip varchar(64) NOT NULL,
      environment varchar(24) NOT NULL, criticality varchar(16) NOT NULL, health_endpoint varchar(255), metrics_endpoint varchar(255),
      dependencies jsonb NOT NULL, backup_policy varchar(128), recovery_priority integer NOT NULL DEFAULT 100,
      rto_target varchar(32), rpo_target varchar(32), status varchar(24) NOT NULL DEFAULT 'UNKNOWN', updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE incident (
      id uuid PRIMARY KEY, incident_code varchar(64) UNIQUE NOT NULL, title varchar(255) NOT NULL, severity varchar(16) NOT NULL,
      status varchar(24) NOT NULL DEFAULT 'DETECTED', environment varchar(24) NOT NULL, service_codes jsonb NOT NULL,
      tenant_impact varchar(64), customer_impact varchar(255), detected_at timestamptz NOT NULL DEFAULT now(), acknowledged_at timestamptz,
      mitigated_at timestamptz, resolved_at timestamptz, owner_id varchar(128), commander_id varchar(128), root_cause text,
      resolution_summary text, correlation_id varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE incident_event (
      id uuid PRIMARY KEY, incident_id uuid NOT NULL REFERENCES incident(id) ON DELETE RESTRICT, event_type varchar(64) NOT NULL,
      actor_id varchar(128), payload_safe jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE readiness_gate (
      gate_code varchar(64) PRIMARY KEY, status varchar(24) NOT NULL DEFAULT 'NOT_STARTED', evidence jsonb NOT NULL,
      owner varchar(128), reviewer varchar(128), approved_at timestamptz, expires_at timestamptz, blocking_findings jsonb NOT NULL,
      waiver_reference varchar(255), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE backup_verification (
      id uuid PRIMARY KEY, system_code varchar(96) NOT NULL, backup_reference varchar(512) NOT NULL,
      state varchar(24) NOT NULL DEFAULT 'CURRENT_UNVERIFIED', checksum varchar(128), encrypted boolean NOT NULL DEFAULT true,
      off_server boolean NOT NULL DEFAULT false, restore_tested boolean NOT NULL DEFAULT false, restore_result jsonb NOT NULL,
      last_verified_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_incident_status ON incident(status, severity, detected_at)")
    op.execute("CREATE INDEX ix_backup_verification_state ON backup_verification(system_code, state)")


def downgrade() -> None:
    for table in ("backup_verification", "readiness_gate", "incident_event", "incident", "service_inventory"):
        op.drop_table(table)
