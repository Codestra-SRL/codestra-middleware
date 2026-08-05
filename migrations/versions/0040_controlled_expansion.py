"""Controlled production expansion stages and observation gates."""
from alembic import op

revision = "0040_controlled_expansion"
down_revision = "0039_operations_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE expansion_stage (
      id uuid PRIMARY KEY, stage_code varchar(64) UNIQUE NOT NULL, status varchar(32) NOT NULL DEFAULT 'PLANNED',
      limits jsonb NOT NULL, approval_reference varchar(255), observation_start timestamptz, observation_end timestamptz,
      gate_outcome varchar(24), stop_reason varchar(512), correlation_id varchar(128) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE expansion_observation (
      id uuid PRIMARY KEY, stage_id uuid NOT NULL REFERENCES expansion_stage(id) ON DELETE RESTRICT,
      outcome varchar(24) NOT NULL, snapshot jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_expansion_observation_stage ON expansion_observation(stage_id, created_at)")


def downgrade() -> None:
    op.drop_table("expansion_observation")
    op.drop_table("expansion_stage")
