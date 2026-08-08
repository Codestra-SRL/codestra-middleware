"""Durable Hootsuite OAuth state ledger.

Revision ID: 0035_hootsuite_oauth_state
Revises: 0034_social_staging
"""

from alembic import op

revision = "0035_hootsuite_oauth_state"
down_revision = "0034_social_staging"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE hootsuite_oauth_states (
        state_hash char(64) PRIMARY KEY,
        tenant_reference text NOT NULL,
        nonce_hash char(64) NOT NULL,
        issued_at timestamptz NOT NULL,
        expires_at timestamptz NOT NULL,
        consumed_at timestamptz,
        status text NOT NULL,
        CONSTRAINT ck_hootsuite_oauth_state_status
          CHECK (status IN ('ISSUED','CONSUMED','EXPIRED')),
        CONSTRAINT ck_hootsuite_oauth_state_consumption
          CHECK ((status='CONSUMED') = (consumed_at IS NOT NULL))
    )""")
    op.execute(
        "CREATE INDEX ix_hootsuite_oauth_state_expiry "
        "ON hootsuite_oauth_states(status,expires_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_hootsuite_oauth_state_expiry")
    op.execute("DROP TABLE hootsuite_oauth_states")
