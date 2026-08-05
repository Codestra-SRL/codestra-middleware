"""Voice AI and AI governance foundation."""
from alembic import op

revision = "0047_voice_ai_governance_foundation"
down_revision = "0046_mobile_platform_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE voice_session (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL, campaign_code varchar(96) NOT NULL,
      direction varchar(16) NOT NULL, status varchar(32) NOT NULL DEFAULT 'REQUESTED', idempotency_key varchar(255) UNIQUE NOT NULL,
      correlation_id varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE voice_callback_request (
      id uuid PRIMARY KEY, session_id varchar(128) NOT NULL, tenant_id varchar(128) NOT NULL, phone varchar(64) NOT NULL,
      scheduled_at varchar(64) NOT NULL, status varchar(24) NOT NULL DEFAULT 'REQUESTED', idempotency_key varchar(255) UNIQUE NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE ai_governance_asset (
      id uuid PRIMARY KEY, asset_type varchar(32) NOT NULL, code varchar(128) NOT NULL, version integer NOT NULL DEFAULT 1,
      status varchar(24) NOT NULL DEFAULT 'DRAFT', schema_reference varchar(255), model_reference varchar(255), definition jsonb NOT NULL DEFAULT '{}',
      created_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_ai_governance_asset_version UNIQUE (asset_type, code, version)
    )""")
    op.execute("""CREATE TABLE ai_evaluation_run (
      id uuid PRIMARY KEY, tenant_id varchar(128), asset_id uuid NOT NULL REFERENCES ai_governance_asset(id) ON DELETE RESTRICT,
      dataset_code varchar(128) NOT NULL, status varchar(24) NOT NULL DEFAULT 'QUEUED', metrics jsonb NOT NULL DEFAULT '{}',
      gate_outcome varchar(24), created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_voice_session_tenant_status ON voice_session(tenant_id, status)")
    op.execute("CREATE INDEX ix_ai_evaluation_asset ON ai_evaluation_run(asset_id, status)")


def downgrade() -> None:
    op.drop_table("ai_evaluation_run")
    op.drop_table("ai_governance_asset")
    op.drop_table("voice_callback_request")
    op.drop_table("voice_session")
