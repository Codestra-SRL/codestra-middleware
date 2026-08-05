"""Enterprise release management foundation."""
from alembic import op

revision = "0066_release_management"
down_revision = "0065_commercial_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE release_record (
      id uuid PRIMARY KEY, version varchar(64) NOT NULL, release_type varchar(32) NOT NULL,
      environment varchar(24) NOT NULL DEFAULT 'STAGING', state varchar(32) NOT NULL DEFAULT 'DRAFT',
      rollback_version varchar(64) NOT NULL DEFAULT '', artifact_checksum varchar(128) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE release_gate (
      id uuid PRIMARY KEY, release_id uuid NOT NULL, gate varchar(48) NOT NULL, outcome varchar(24) NOT NULL DEFAULT 'BLOCKED',
      evidence_reference varchar(255) NOT NULL DEFAULT '', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE release_approval (
      id uuid PRIMARY KEY, release_id uuid NOT NULL, reviewer_id varchar(128) NOT NULL, role varchar(32) NOT NULL,
      decision varchar(24) NOT NULL DEFAULT 'PENDING', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_release_record_scope ON release_record(environment,state)")
    op.execute("CREATE INDEX ix_release_gate_scope ON release_gate(release_id,outcome)")
    op.execute("CREATE INDEX ix_release_approval_scope ON release_approval(release_id,decision)")


def downgrade() -> None:
    op.drop_index("ix_release_approval_scope", table_name="release_approval")
    op.drop_index("ix_release_gate_scope", table_name="release_gate")
    op.drop_index("ix_release_record_scope", table_name="release_record")
    op.drop_table("release_approval")
    op.drop_table("release_gate")
    op.drop_table("release_record")
