"""Merge sales lead and TTS runtime migration heads.

Revision ID: 0034_merge_sales_tts_heads
Revises: 0033_sales_lead_foundation, 0033_tts_job_runtime
"""

revision = "0034_merge_sales_tts_heads"
down_revision = ("0033_sales_lead_foundation", "0033_tts_job_runtime")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
