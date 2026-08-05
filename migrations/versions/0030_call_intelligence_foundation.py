"""Call Intelligence canonical records.

Revision ID: 0030_call_intelligence
Revises: 0029_merge_lead_recording_heads
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0030_call_intelligence"
down_revision = "0029_merge_lead_recording_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "call_intelligence_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True)),
        sa.Column("vicidial_call_id", sa.String(128), nullable=False),
        sa.Column("vicidial_uniqueid", sa.String(128), nullable=False),
        sa.Column("odoo_lead_id", sa.BigInteger()),
        sa.Column("campaign_id", sa.String(64)),
        sa.Column("agent_user", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("language", sa.String(16)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("recording_reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True)),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True)),
        sa.Column("qa_review_id", postgresql.UUID(as_uuid=True)),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_class", sa.String(32)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("safe_error_message", sa.String(512)),
        sa.UniqueConstraint(
            "tenant_id", "vicidial_uniqueid", name="uq_call_intelligence_external_key"
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_call_intelligence_idempotency"),
    )
    op.create_index(
        "ix_call_intelligence_status",
        "call_intelligence_jobs",
        ["tenant_id", "status", "created_at"],
    )
    op.create_table(
        "call_recording_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_intelligence_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("recording_id", sa.String(128), nullable=False),
        sa.Column("storage_reference", sa.LargeBinary(), nullable=False),
        sa.Column("format", sa.String(16), nullable=False),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("checksum", sa.String(71)),
        sa.Column("recorded_at", sa.DateTime(timezone=True)),
        sa.Column("retention_expires_at", sa.DateTime(timezone=True)),
        sa.Column("access_policy", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "provider", "recording_id", name="uq_recording_provider_id"
        ),
    )
    op.create_table(
        "call_transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_intelligence_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("model_code", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("language", sa.String(16)),
        sa.Column("language_confidence", sa.Float()),
        sa.Column("speaker_count", sa.Integer()),
        sa.Column(
            "transcript_text_encrypted_or_protected", sa.LargeBinary(), nullable=False
        ),
        sa.Column("segments", postgresql.JSONB(), nullable=False),
        sa.Column("redaction_status", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_table(
        "call_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_intelligence_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("model_code", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sentiment", postgresql.JSONB(), nullable=False),
        sa.Column("disposition_recommendation", sa.String(128)),
        sa.Column("objections", postgresql.JSONB(), nullable=False),
        sa.Column("products_discussed", postgresql.JSONB(), nullable=False),
        sa.Column("commitments", postgresql.JSONB(), nullable=False),
        sa.Column("callback_recommendation", postgresql.JSONB(), nullable=False),
        sa.Column("next_best_action", sa.Text()),
        sa.Column("compliance_findings", postgresql.JSONB(), nullable=False),
        sa.Column("coaching_recommendations", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("raw_result_safe", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_table(
        "call_qa_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_intelligence_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("scorecard_version", sa.String(64), nullable=False),
        *[
            sa.Column(f"{name}_score", sa.Integer())
            for name in (
                "greeting",
                "identity_verification",
                "disclosure",
                "professionalism",
                "product_knowledge",
                "listening",
                "objection_handling",
                "accuracy",
                "closing",
                "documentation",
                "compliance",
            )
        ],
        sa.Column("overall_score", sa.Integer()),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_table(
        "call_compliance_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_intelligence_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("evidence_reference", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assigned_to", sa.String(128)),
        sa.Column("resolved_by", sa.String(128)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "call_job_id",
            "alert_type",
            "evidence_reference",
            name="uq_call_compliance_evidence",
        ),
    )
    op.create_table(
        "call_intelligence_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_intelligence_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("service_code", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("error_class", sa.String(32)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("safe_error_message", sa.String(512)),
        sa.UniqueConstraint(
            "call_job_id", "stage", "attempt_number", name="uq_call_attempt"
        ),
    )
    op.create_table(
        "call_intelligence_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "call_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("call_intelligence_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(32), nullable=False),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("actor_reference", sa.String(128), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    for table in (
        "call_intelligence_audit",
        "call_intelligence_attempts",
        "call_compliance_alerts",
        "call_qa_scores",
        "call_analyses",
        "call_transcripts",
        "call_recording_references",
        "call_intelligence_jobs",
    ):
        op.drop_table(table)
