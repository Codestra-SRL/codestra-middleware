"""Beyvra transactional email durable control plane.

Revision ID: 20260819_01
Revises: 0048_agent_call_realtime
"""
from alembic import op
import sqlalchemy as sa

revision = "20260819_01"
down_revision = "0048_agent_call_realtime"
branch_labels = None
depends_on = None

status = sa.Enum("CREATED", "QUEUED", "PROCESSING", "SUBMITTED", "SENT", "DELIVERED", "DEFERRED", "BOUNCED_SOFT", "BOUNCED_HARD", "COMPLAINED", "SUPPRESSED", "FAILED", "DEAD_LETTER", name="emailstatus")


def upgrade():
    op.create_table("email_template_version", sa.Column("template_id", sa.String(100), primary_key=True), sa.Column("version", sa.Integer, primary_key=True), sa.Column("locale", sa.String(20), primary_key=True), sa.Column("category", sa.String(30), nullable=False), sa.Column("subject", sa.String(255), nullable=False), sa.Column("text_body", sa.Text, nullable=False), sa.Column("html_body", sa.Text, nullable=False), sa.Column("required_variables", sa.JSON, nullable=False), sa.Column("active", sa.Boolean, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("email_notification", sa.Column("notification_id", sa.String(36), primary_key=True), sa.Column("event_id", sa.String(200), nullable=False), sa.Column("correlation_id", sa.String(200), nullable=False), sa.Column("idempotency_key", sa.String(200), nullable=False), sa.Column("user_id", sa.String(200), nullable=False), sa.Column("account_id", sa.String(200), nullable=False), sa.Column("tenant_id", sa.String(200), nullable=False), sa.Column("template_id", sa.String(100), nullable=False), sa.Column("template_version", sa.Integer, nullable=False), sa.Column("recipient", sa.String(320), nullable=False), sa.Column("recipient_hash", sa.String(64), nullable=False), sa.Column("sender", sa.String(320), nullable=False), sa.Column("event_type", sa.String(100), nullable=False), sa.Column("category", sa.String(30), nullable=False), sa.Column("locale", sa.String(20), nullable=False), sa.Column("parameters", sa.JSON, nullable=False), sa.Column("status", status, nullable=False), sa.Column("attempt_count", sa.Integer, nullable=False), sa.Column("last_error_class", sa.String(80)), sa.Column("provider_message_id", sa.String(255)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("queued_at", sa.DateTime(timezone=True)), sa.Column("sent_at", sa.DateTime(timezone=True)), sa.Column("delivered_at", sa.DateTime(timezone=True)), sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_email_notification_tenant_idempotency"))
    for name, columns in (("ix_email_notification_event", ["tenant_id", "event_id"]), ("ix_email_notification_provider", ["provider_message_id"]), ("ix_email_notification_recipient", ["tenant_id", "recipient_hash"]), ("ix_email_notification_created", ["created_at"]), ("ix_email_notification_status", ["status"])):
        op.create_index(name, "email_notification", columns)
    op.create_table("email_outbox", sa.Column("notification_id", sa.String(36), sa.ForeignKey("email_notification.notification_id"), primary_key=True), sa.Column("status", sa.String(30), nullable=False), sa.Column("available_at", sa.DateTime(timezone=True), nullable=False), sa.Column("lease_owner", sa.String(100)), sa.Column("lease_expires_at", sa.DateTime(timezone=True)), sa.Column("attempt_count", sa.Integer, nullable=False), sa.Column("last_error_class", sa.String(80)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_email_outbox_claim", "email_outbox", ["status", "available_at", "lease_expires_at"])
    op.create_table("email_delivery_event", sa.Column("id", sa.String(36), primary_key=True), sa.Column("provider_event_id", sa.String(255), nullable=False, unique=True), sa.Column("provider_message_id", sa.String(255), nullable=False), sa.Column("notification_id", sa.String(36), sa.ForeignKey("email_notification.notification_id"), nullable=False), sa.Column("correlation_id", sa.String(200), nullable=False), sa.Column("event_type", sa.String(80), nullable=False), sa.Column("normalized_status", status, nullable=False), sa.Column("payload_digest", sa.String(64), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("received_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_email_delivery_provider_message", "email_delivery_event", ["provider_message_id"])
    op.create_table("email_dead_letter", sa.Column("notification_id", sa.String(36), sa.ForeignKey("email_notification.notification_id"), primary_key=True), sa.Column("error_class", sa.String(80), nullable=False), sa.Column("error_digest", sa.String(64), nullable=False), sa.Column("attempt_count", sa.Integer, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("replayed_at", sa.DateTime(timezone=True)))
    op.create_table("email_suppression", sa.Column("id", sa.String(36), primary_key=True), sa.Column("tenant_id", sa.String(200), nullable=False), sa.Column("recipient_hash", sa.String(64), nullable=False), sa.Column("reason", sa.String(40), nullable=False), sa.Column("active", sa.Boolean, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("tenant_id", "recipient_hash", "reason", name="uq_email_suppression_boundary"))


def downgrade():
    for table in ("email_suppression", "email_dead_letter", "email_delivery_event", "email_outbox", "email_notification", "email_template_version"):
        op.drop_table(table)
    status.drop(op.get_bind(), checkfirst=True)
