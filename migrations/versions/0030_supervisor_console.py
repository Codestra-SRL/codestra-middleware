"""Supervisor console operational read models and audited workflow state.

Revision ID: 0030_supervisor_console
Revises: 0029_merge_lead_recording_heads
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030_supervisor_console"
down_revision = "0029_merge_lead_recording_heads"
branch_labels = None
depends_on = None


def scoped_table(name: str, *columns: sa.Column, unique: tuple[str, ...] = ()) -> None:
    constraints = []
    if unique:
        constraints.append(
            sa.UniqueConstraint(
                "tenant_id", "workspace_id", *unique, name=f"uq_{name}_scope"
            )
        )
    op.create_table(
        name,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("workspace_id", sa.String(64), nullable=False),
        *columns,
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        *constraints,
    )
    op.create_index(f"ix_{name}_scope", name, ["tenant_id", "workspace_id"])


def upgrade() -> None:
    scoped_table(
        "supervisor_teams",
        sa.Column("external_key", sa.String(96), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        unique=("external_key",),
    )
    scoped_table(
        "supervisor_team_members",
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        unique=("team_id", "subject_id", "role"),
    )
    scoped_table(
        "supervisor_campaign_assignments",
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campaign_key", sa.String(96), nullable=False),
        unique=("team_id", "campaign_key"),
    )
    scoped_table(
        "supervisor_sessions",
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(256), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    scoped_table(
        "supervisor_monitoring_events",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("accessed_fields", postgresql.JSONB, nullable=False),
    )
    scoped_table(
        "supervisor_commands",
        sa.Column("command_type", sa.String(64), nullable=False),
        sa.Column("target_key", sa.String(128), nullable=False),
        sa.Column("reason", sa.String(256), nullable=False),
        sa.Column("idempotency_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        unique=("idempotency_hash",),
    )
    scoped_table(
        "supervisor_command_attempts",
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        unique=("command_id", "attempt"),
    )
    scoped_table(
        "agent_state_events",
        sa.Column("agent_key", sa.String(96), nullable=False),
        sa.Column("team_key", sa.String(96), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("sequence", sa.BigInteger, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        unique=("agent_key", "sequence"),
    )
    scoped_table(
        "agent_performance_snapshots",
        sa.Column("agent_key", sa.String(96), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB, nullable=False),
        unique=("agent_key", "window_start"),
    )
    scoped_table(
        "agent_adherence_records",
        sa.Column("agent_key", sa.String(96), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    scoped_table(
        "agent_schedules",
        sa.Column("agent_key", sa.String(96), nullable=False),
        sa.Column("activity_type", sa.String(32), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
    )
    scoped_table(
        "coaching_records",
        sa.Column("agent_key", sa.String(96), nullable=False),
        sa.Column("supervisor_subject", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("topic", sa.String(256), nullable=False),
        sa.Column("notes_ciphertext", sa.LargeBinary),
    )
    scoped_table(
        "coaching_events",
        sa.Column("coaching_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_subject", sa.String(128), nullable=False),
    )
    scoped_table(
        "callback_management_events",
        sa.Column("callback_key", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("idempotency_hash", sa.String(64), nullable=False),
        unique=("idempotency_hash",),
    )
    scoped_table(
        "transfer_events",
        sa.Column("call_key", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("sequence", sa.BigInteger, nullable=False),
        unique=("call_key", "sequence"),
    )
    scoped_table(
        "operational_thresholds",
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("value", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        unique=("metric",),
    )
    scoped_table(
        "supervisor_saved_views",
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("definition", postgresql.JSONB, nullable=False),
        unique=("subject_id", "name"),
    )


def downgrade() -> None:
    for name in reversed(
        (
            "supervisor_teams",
            "supervisor_team_members",
            "supervisor_campaign_assignments",
            "supervisor_sessions",
            "supervisor_monitoring_events",
            "supervisor_commands",
            "supervisor_command_attempts",
            "agent_state_events",
            "agent_performance_snapshots",
            "agent_adherence_records",
            "agent_schedules",
            "coaching_records",
            "coaching_events",
            "callback_management_events",
            "transfer_events",
            "operational_thresholds",
            "supervisor_saved_views",
        )
    ):
        op.drop_table(name)
