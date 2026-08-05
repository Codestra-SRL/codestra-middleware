"""Add tenant-scoped enterprise identity storage.

Revision ID: 0030_enterprise_identity_core
Revises: 0029_merge_lead_recording_heads
"""

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030_enterprise_identity_core"
down_revision = "0029_merge_lead_recording_heads"
branch_labels = None
depends_on = None


def _governed_columns() -> list[Any]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_%(table_name)s_version"),
    ]


def upgrade() -> None:
    op.create_table(
        "iam_tenant",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(96), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_iam_tenant_version"),
        sa.CheckConstraint("status IN ('ACTIVE','SUSPENDED','CLOSED')", name="ck_iam_tenant_status"),
    )
    op.create_table(
        "iam_workspace",
        *_governed_columns(),
        sa.Column("slug", sa.String(96), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["iam_tenant.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_iam_workspace_tenant_slug"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_iam_workspace_tenant_id"),
    )
    op.create_table(
        "iam_principal",
        *_governed_columns(),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("principal_type", sa.String(24), nullable=False),
        sa.Column("email_normalized", sa.String(320)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["iam_tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id"],
            ["iam_workspace.tenant_id", "iam_workspace.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "workspace_id", "subject", name="uq_iam_principal_scope_subject"),
        sa.CheckConstraint(
            "principal_type IN ('USER','SERVICE_ACCOUNT','AI_EMPLOYEE','API_CLIENT')",
            name="ck_iam_principal_type",
        ),
    )
    op.create_table(
        "iam_role_binding",
        *_governed_columns(),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_key", sa.String(64), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["principal_id"], ["iam_principal.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "principal_id", "role_key", "department_id",
            name="uq_iam_role_binding_scope",
        ),
    )
    op.create_table(
        "iam_session",
        *_governed_columns(),
        sa.Column("principal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_session_id_hash", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("device_fingerprint_hash", sa.String(64)),
        sa.Column("last_ip_prefix", sa.String(64)),
        sa.ForeignKeyConstraint(["principal_id"], ["iam_principal.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider_session_id_hash", name="uq_iam_session_provider_hash"),
        sa.CheckConstraint("idle_expires_at <= absolute_expires_at", name="ck_iam_session_expiry"),
    )
    op.create_index("ix_iam_principal_scope", "iam_principal", ["tenant_id", "workspace_id", "status"])
    op.create_index("ix_iam_session_active", "iam_session", ["tenant_id", "workspace_id", "principal_id", "revoked_at"])


def downgrade() -> None:
    op.drop_index("ix_iam_session_active", table_name="iam_session")
    op.drop_index("ix_iam_principal_scope", table_name="iam_principal")
    op.drop_table("iam_session")
    op.drop_table("iam_role_binding")
    op.drop_table("iam_principal")
    op.drop_table("iam_workspace")
    op.drop_table("iam_tenant")
