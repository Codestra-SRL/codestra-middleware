"""Complete Wave 1 identity governance columns.

Revision ID: 0033_wave1_identity_governance
Revises: 0032_enterprise_core_completion
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0033_wave1_identity_governance"
down_revision = "0032_enterprise_core_completion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "iam_api_key",
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.add_column("iam_api_key", sa.Column("updated_by", sa.String(128)))
    op.add_column(
        "iam_api_key",
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.execute("""
        UPDATE iam_api_key
        SET updated_at=created_at, updated_by=created_by
        WHERE updated_at IS NULL OR updated_by IS NULL
    """)
    op.alter_column("iam_api_key", "updated_at", nullable=False)
    op.alter_column("iam_api_key", "updated_by", nullable=False)

    op.add_column(
        "iam_access_review",
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )

    op.add_column(
        "iam_access_review_item",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "iam_access_review_item",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True)),
    )
    op.add_column(
        "iam_access_review_item",
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "iam_access_review_item",
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.add_column("iam_access_review_item", sa.Column("created_by", sa.String(128)))
    op.add_column("iam_access_review_item", sa.Column("updated_by", sa.String(128)))
    op.add_column(
        "iam_access_review_item",
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "iam_access_review_item",
        sa.Column("version", sa.Integer()),
    )
    op.add_column(
        "iam_access_review_item",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True)),
    )
    op.execute("""
        UPDATE iam_access_review_item item
        SET tenant_id=review.tenant_id,
            workspace_id=review.workspace_id,
            created_at=review.created_at,
            updated_at=COALESCE(review.updated_at, review.created_at),
            created_by=review.created_by,
            updated_by=review.updated_by,
            version=1,
            audit_id=gen_random_uuid()
        FROM iam_access_review review
        WHERE review.id=item.review_id
          AND (item.tenant_id IS NULL OR item.workspace_id IS NULL)
    """)
    for column in (
        "tenant_id",
        "workspace_id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "version",
        "audit_id",
    ):
        op.alter_column("iam_access_review_item", column, nullable=False)
    op.create_foreign_key(
        "fk_iam_review_item_tenant",
        "iam_access_review_item",
        "iam_tenant",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_iam_review_item_workspace_scope",
        "iam_access_review_item",
        "iam_workspace",
        ["tenant_id", "workspace_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_iam_access_review_item_version",
        "iam_access_review_item",
        "version >= 1",
    )
    op.create_index(
        "ix_iam_access_review_item_scope",
        "iam_access_review_item",
        ["tenant_id", "workspace_id", "review_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_iam_access_review_item_scope",
        table_name="iam_access_review_item",
    )
    op.drop_constraint(
        "ck_iam_access_review_item_version",
        "iam_access_review_item",
        type_="check",
    )
    op.drop_constraint(
        "fk_iam_review_item_workspace_scope",
        "iam_access_review_item",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_iam_review_item_tenant",
        "iam_access_review_item",
        type_="foreignkey",
    )
    for column in (
        "audit_id",
        "version",
        "deleted_at",
        "updated_by",
        "created_by",
        "updated_at",
        "created_at",
        "workspace_id",
        "tenant_id",
    ):
        op.drop_column("iam_access_review_item", column)
    op.drop_column("iam_access_review", "deleted_at")
    op.drop_column("iam_api_key", "deleted_at")
    op.drop_column("iam_api_key", "updated_by")
    op.drop_column("iam_api_key", "updated_at")
