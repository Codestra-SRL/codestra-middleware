"""Persist n8n lifecycle evidence and the complete allocation contract.

Revision ID: 0019_execution_trace_allocator
Revises: (0018_campaign_registry_grants, 0018_campaign_search_aliases)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0019_execution_trace_allocator"
down_revision = ("0018_campaign_registry_grants", "0018_campaign_search_aliases")
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB


def upgrade() -> None:
    op.create_table(
        "n8n_execution",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("execution_id", sa.String(128), nullable=False, unique=True),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("workflow_key", sa.String(128), nullable=False),
        sa.Column("workflow_version", sa.String(32), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="REGISTERED"),
        sa.Column("registration_hash", sa.String(64), nullable=False),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "event_id", "workflow_key", name="uq_n8n_execution_event_workflow"
        ),
        sa.CheckConstraint(
            "status IN ('REGISTERED','RUNNING','SUCCEEDED','FAILED','CANCELLED')",
            name="ck_n8n_execution_status",
        ),
    )
    op.create_index("ix_n8n_execution_event_id", "n8n_execution", ["event_id"])
    op.create_index(
        "ix_n8n_execution_correlation_id", "n8n_execution", ["correlation_id"]
    )
    op.create_table(
        "n8n_acknowledgement",
        sa.Column("acknowledgement_id", UUID, primary_key=True),
        sa.Column("execution_id", sa.String(128), nullable=False, unique=True),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("acknowledgement_hash", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_n8n_ack_event_id", "n8n_acknowledgement", ["event_id"])
    op.create_index(
        "ix_n8n_ack_correlation_id", "n8n_acknowledgement", ["correlation_id"]
    )
    op.create_table(
        "integration_result",
        sa.Column("result_id", UUID, primary_key=True),
        sa.Column("execution_id", sa.String(128), nullable=False, unique=True),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_integration_result_event_id", "integration_result", ["event_id"]
    )
    op.create_index(
        "ix_integration_result_correlation_id", "integration_result", ["correlation_id"]
    )
    op.create_table(
        "integration_trace",
        sa.Column("trace_id", UUID, primary_key=True),
        sa.Column("correlation_id", sa.String(128), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("identity", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "correlation_id", "stage", "identity", name="uq_integration_trace_stage"
        ),
    )
    op.create_index(
        "ix_integration_trace_correlation_id", "integration_trace", ["correlation_id"]
    )
    op.create_table(
        "agent_lead_extension_destination_allocation",
        sa.Column("allocation_id", UUID, primary_key=True),
        sa.Column("idempotency_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("agent_id", sa.String(128), nullable=False),
        sa.Column("lead_id", sa.String(128), nullable=False),
        sa.Column("business_unit", sa.String(64), nullable=False),
        sa.Column("campaign_id", sa.String(64), nullable=False),
        sa.Column(
            "extension_reservation_id",
            UUID,
            sa.ForeignKey("telephony_extension_reservation.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("extension", sa.Integer, nullable=False),
        sa.Column("destination", sa.String(128), nullable=False),
        sa.Column("destination_type", sa.String(32), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="LEASED"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('LEASED','COMMITTED','RELEASED','EXPIRED')",
            name="ck_complete_allocation_state",
        ),
    )
    for name, column in (
        ("uq_active_allocation_agent", "agent_id"),
        ("uq_active_allocation_lead", "lead_id"),
        ("uq_active_allocation_destination", "destination"),
    ):
        op.create_index(
            name,
            "agent_lead_extension_destination_allocation",
            [column],
            unique=True,
            postgresql_where=sa.text("state IN ('LEASED','COMMITTED')"),
        )


def downgrade() -> None:
    for name in (
        "uq_active_allocation_destination",
        "uq_active_allocation_lead",
        "uq_active_allocation_agent",
    ):
        op.drop_index(name, table_name="agent_lead_extension_destination_allocation")
    op.drop_table("agent_lead_extension_destination_allocation")
    op.drop_index("ix_integration_trace_correlation_id", table_name="integration_trace")
    op.drop_table("integration_trace")
    op.drop_index(
        "ix_integration_result_correlation_id", table_name="integration_result"
    )
    op.drop_index("ix_integration_result_event_id", table_name="integration_result")
    op.drop_table("integration_result")
    op.drop_index("ix_n8n_ack_correlation_id", table_name="n8n_acknowledgement")
    op.drop_index("ix_n8n_ack_event_id", table_name="n8n_acknowledgement")
    op.drop_table("n8n_acknowledgement")
    op.drop_index("ix_n8n_execution_correlation_id", table_name="n8n_execution")
    op.drop_index("ix_n8n_execution_event_id", table_name="n8n_execution")
    op.drop_table("n8n_execution")
