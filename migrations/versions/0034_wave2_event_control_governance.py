"""Complete Wave 2 event control-plane governance columns.

Revision ID: 0034_wave2_event_governance
Revises: 0033_wave1_identity_governance
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_wave2_event_governance"
down_revision = "0033_wave1_identity_governance"
branch_labels = None
depends_on = None


def _add_common_columns(table: str) -> None:
    op.add_column(table, sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column(table, sa.Column("version", sa.Integer()))
    op.add_column(table, sa.Column("audit_id", postgresql.UUID(as_uuid=True)))


def _require_common_columns(table: str) -> None:
    op.alter_column(table, "version", nullable=False)
    op.alter_column(table, "audit_id", nullable=False)
    op.create_check_constraint(f"ck_{table}_version", table, "version >= 1")


def upgrade() -> None:
    # The append-only trigger is removed only inside this transactional migration
    # so existing immutable rows can receive governance metadata. It is recreated
    # before the transaction commits.
    op.execute("DROP TRIGGER enterprise_event_immutable ON enterprise_event")
    op.add_column(
        "enterprise_event", sa.Column("created_at", sa.DateTime(timezone=True))
    )
    op.add_column(
        "enterprise_event", sa.Column("updated_at", sa.DateTime(timezone=True))
    )
    op.add_column("enterprise_event", sa.Column("created_by", sa.String(128)))
    op.add_column("enterprise_event", sa.Column("updated_by", sa.String(128)))
    _add_common_columns("enterprise_event")
    op.execute("""
        UPDATE enterprise_event
        SET created_at=recorded_at,
            updated_at=recorded_at,
            created_by=recorded_by,
            updated_by=recorded_by,
            version=1,
            audit_id=gen_random_uuid()
    """)
    for column in (
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    ):
        op.alter_column("enterprise_event", column, nullable=False)
    _require_common_columns("enterprise_event")
    op.execute("""
        CREATE TRIGGER enterprise_event_immutable
        BEFORE UPDATE OR DELETE ON enterprise_event
        FOR EACH ROW EXECUTE FUNCTION reject_enterprise_event_mutation()
    """)

    op.add_column(
        "enterprise_event_replay", sa.Column("created_by", sa.String(128))
    )
    op.add_column(
        "enterprise_event_replay", sa.Column("updated_by", sa.String(128))
    )
    _add_common_columns("enterprise_event_replay")
    op.execute("""
        UPDATE enterprise_event_replay
        SET created_by=requested_by,
            updated_by=requested_by,
            version=1,
            audit_id=gen_random_uuid()
    """)
    op.alter_column("enterprise_event_replay", "created_by", nullable=False)
    op.alter_column("enterprise_event_replay", "updated_by", nullable=False)
    _require_common_columns("enterprise_event_replay")

    op.add_column(
        "enterprise_event_subscription",
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "enterprise_event_subscription", sa.Column("updated_by", sa.String(128))
    )
    _add_common_columns("enterprise_event_subscription")
    op.execute("""
        UPDATE enterprise_event_subscription
        SET updated_at=created_at,
            updated_by=created_by,
            version=1,
            audit_id=gen_random_uuid()
    """)
    op.alter_column("enterprise_event_subscription", "updated_at", nullable=False)
    op.alter_column("enterprise_event_subscription", "updated_by", nullable=False)
    _require_common_columns("enterprise_event_subscription")

    op.add_column(
        "enterprise_event_delivery", sa.Column("created_by", sa.String(128))
    )
    op.add_column(
        "enterprise_event_delivery", sa.Column("updated_by", sa.String(128))
    )
    _add_common_columns("enterprise_event_delivery")
    op.execute("""
        UPDATE enterprise_event_delivery delivery
        SET created_by=subscription.created_by,
            updated_by=subscription.created_by,
            version=1,
            audit_id=gen_random_uuid()
        FROM enterprise_event_subscription subscription
        WHERE subscription.id=delivery.subscription_id
    """)
    op.alter_column("enterprise_event_delivery", "created_by", nullable=False)
    op.alter_column("enterprise_event_delivery", "updated_by", nullable=False)
    _require_common_columns("enterprise_event_delivery")

    op.create_index(
        "ix_enterprise_event_replay_scope_status",
        "enterprise_event_replay",
        ["tenant_id", "workspace_id", "status", "next_attempt_at"],
    )
    op.create_index(
        "ix_enterprise_event_subscription_scope_enabled",
        "enterprise_event_subscription",
        ["tenant_id", "workspace_id", "enabled"],
    )


def _drop_common_columns(table: str) -> None:
    op.drop_constraint(f"ck_{table}_version", table, type_="check")
    op.drop_column(table, "audit_id")
    op.drop_column(table, "version")
    op.drop_column(table, "deleted_at")


def downgrade() -> None:
    op.drop_index(
        "ix_enterprise_event_subscription_scope_enabled",
        table_name="enterprise_event_subscription",
    )
    op.drop_index(
        "ix_enterprise_event_replay_scope_status",
        table_name="enterprise_event_replay",
    )

    _drop_common_columns("enterprise_event_delivery")
    op.drop_column("enterprise_event_delivery", "updated_by")
    op.drop_column("enterprise_event_delivery", "created_by")

    _drop_common_columns("enterprise_event_subscription")
    op.drop_column("enterprise_event_subscription", "updated_by")
    op.drop_column("enterprise_event_subscription", "updated_at")

    _drop_common_columns("enterprise_event_replay")
    op.drop_column("enterprise_event_replay", "updated_by")
    op.drop_column("enterprise_event_replay", "created_by")

    op.execute("DROP TRIGGER enterprise_event_immutable ON enterprise_event")
    _drop_common_columns("enterprise_event")
    op.drop_column("enterprise_event", "updated_by")
    op.drop_column("enterprise_event", "created_by")
    op.drop_column("enterprise_event", "updated_at")
    op.drop_column("enterprise_event", "created_at")
    op.execute("""
        CREATE TRIGGER enterprise_event_immutable
        BEFORE UPDATE OR DELETE ON enterprise_event
        FOR EACH ROW EXECUTE FUNCTION reject_enterprise_event_mutation()
    """)
