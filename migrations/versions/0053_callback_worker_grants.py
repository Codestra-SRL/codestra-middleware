"""Grant callback tables to the bounded callback worker roles.

Revision ID: 0053_callback_worker_grants
Revises: 0052_callback_rls_hardening
"""

from alembic import op

revision = "0053_callback_worker_grants"
down_revision = "0052_callback_rls_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    grants = {
        "mw_scheduler": {
            "callback_record": "SELECT,UPDATE",
            "callback_event": "SELECT,INSERT,UPDATE",
            "callback_delivery": "SELECT,INSERT,UPDATE",
        },
        "mw_notification_worker": {
            "callback_record": "SELECT",
            "callback_delivery": "SELECT,UPDATE",
        },
    }
    for role, tables in grants.items():
        for table, privileges in tables.items():
            op.execute(
                f"""DO $$ BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN
                  GRANT {privileges} ON {table} TO {role};
                END IF;
                END $$"""
            )


def downgrade() -> None:
    op.execute("REVOKE ALL PRIVILEGES ON callback_delivery FROM mw_notification_worker")
    op.execute("REVOKE ALL PRIVILEGES ON callback_record FROM mw_notification_worker")
    op.execute("REVOKE ALL PRIVILEGES ON callback_delivery FROM mw_scheduler")
    op.execute("REVOKE ALL PRIVILEGES ON callback_event FROM mw_scheduler")
    op.execute("REVOKE ALL PRIVILEGES ON callback_record FROM mw_scheduler")
