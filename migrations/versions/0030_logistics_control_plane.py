"""Tenant-scoped transportation and logistics control plane."""

from alembic import op

revision = "0030_logistics_control_plane"
down_revision = "0029_merge_lead_recording_heads"
branch_labels = None
depends_on = None

CORE_SQL = r"""
CREATE TABLE logistics_orders (
 public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL,
 workspace_id varchar(128) NOT NULL, external_key varchar(128) NOT NULL,
 customer_external_key varchar(128) NOT NULL, status varchar(32) NOT NULL,
 payload_json jsonb NOT NULL, created_by varchar(128) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id, workspace_id, external_key)
);
CREATE TABLE logistics_shipments (
 public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL,
 workspace_id varchar(128) NOT NULL, external_key varchar(128) NOT NULL,
 order_external_key varchar(128) NOT NULL, status varchar(32) NOT NULL,
 payload_json jsonb NOT NULL, created_by varchar(128) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id, workspace_id, external_key)
);
CREATE INDEX ix_logistics_shipments_scope_status ON logistics_shipments(tenant_id,workspace_id,status);
CREATE TABLE logistics_loads (
 public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL,
 workspace_id varchar(128) NOT NULL, external_key varchar(128) NOT NULL,
 status varchar(32) NOT NULL, shipment_ids jsonb NOT NULL DEFAULT '[]',
 driver_external_key varchar(128), vehicle_external_key varchar(128),
 created_by varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,workspace_id,external_key)
);
CREATE TABLE logistics_status_events (
 id bigserial PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
 shipment_public_id varchar(64) NOT NULL REFERENCES logistics_shipments(public_id),
 from_status varchar(32) NOT NULL, to_status varchar(32) NOT NULL,
 actor_subject varchar(128) NOT NULL, reason varchar(500) NOT NULL DEFAULT '',
 idempotency_key varchar(255) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,shipment_public_id,idempotency_key)
);
CREATE TABLE logistics_exceptions (
 public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
 shipment_public_id varchar(64) NOT NULL REFERENCES logistics_shipments(public_id),
 exception_type varchar(64) NOT NULL, status varchar(32) NOT NULL,
 note text NOT NULL, created_by varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE logistics_claims (
 public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
 external_key varchar(128) NOT NULL, shipment_public_id varchar(64) NOT NULL REFERENCES logistics_shipments(public_id),
 status varchar(32) NOT NULL, reason text NOT NULL, created_by varchar(128) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,workspace_id,external_key)
);
CREATE TABLE logistics_proof_events (
 public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
 shipment_public_id varchar(64) NOT NULL REFERENCES logistics_shipments(public_id), proof_type varchar(32) NOT NULL,
 object_key varchar(255) NOT NULL, content_sha256 char(64) NOT NULL, recipient_name varchar(120) NOT NULL DEFAULT '',
 scan_status varchar(32) NOT NULL DEFAULT 'PENDING', created_by varchar(128) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,object_key)
);
CREATE TABLE logistics_quotes (
 public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
 external_key varchar(128) NOT NULL, status varchar(32) NOT NULL, currency char(3) NOT NULL,
 amount numeric(18,2) NOT NULL, calculation_version varchar(64) NOT NULL, created_by varchar(128) NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(tenant_id,workspace_id,external_key)
);
CREATE TABLE logistics_tracking_tokens (
 token_digest char(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL,
 shipment_public_id varchar(64) NOT NULL REFERENCES logistics_shipments(public_id),
 expires_at timestamptz NOT NULL, revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE logistics_idempotency (
 tenant_id varchar(128) NOT NULL, operation varchar(64) NOT NULL, idempotency_key varchar(255) NOT NULL,
 request_hash char(64) NOT NULL, response_json jsonb NOT NULL, expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(tenant_id,operation,idempotency_key)
);
CREATE TABLE logistics_audit_events (
 id bigserial PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
 actor_subject varchar(128) NOT NULL, action varchar(96) NOT NULL, resource_type varchar(64) NOT NULL,
 resource_public_id varchar(64) NOT NULL, metadata_json jsonb NOT NULL DEFAULT '{}',
 correlation_id varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
"""

AUX_TABLES = (
    "customers",
    "locations",
    "contacts",
    "routes",
    "stops",
    "drivers",
    "vehicles",
    "assignments",
    "tracking_events",
    "rate_cards",
    "quote_items",
    "charges",
    "documents",
    "notifications",
    "driver_settlements",
    "reconciliation",
)


def upgrade() -> None:
    # asyncpg prepares one statement at a time; keep this migration compatible
    # with the production async Alembic environment.
    for statement in CORE_SQL.split(";\n"):
        if statement.strip():
            op.execute(statement)
    for name in AUX_TABLES:
        op.execute(f"""CREATE TABLE logistics_{name} (
          public_id varchar(64) PRIMARY KEY, tenant_id varchar(128) NOT NULL,
          workspace_id varchar(128) NOT NULL, external_key varchar(128) NOT NULL,
          state varchar(32) NOT NULL DEFAULT 'ACTIVE', payload_json jsonb NOT NULL DEFAULT '{{}}',
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE(tenant_id,workspace_id,external_key));""")


def downgrade() -> None:
    for name in reversed(AUX_TABLES):
        op.execute(f"DROP TABLE logistics_{name}")
    for name in (
        "audit_events",
        "idempotency",
        "tracking_tokens",
        "quotes",
        "proof_events",
        "claims",
        "exceptions",
        "status_events",
        "loads",
        "shipments",
        "orders",
    ):
        op.execute(f"DROP TABLE logistics_{name}")
