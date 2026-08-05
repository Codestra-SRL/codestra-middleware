"""Omnichannel support workflow foundation."""

from alembic import op

revision = "0051_support_foundation"
down_revision = "0050_legal_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE support_ticket (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, customer_id varchar(128) NOT NULL,
      subject varchar(255) NOT NULL, status varchar(40) NOT NULL DEFAULT 'NEW', priority varchar(16) NOT NULL DEFAULT 'NORMAL',
      idempotency_key varchar(255) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE support_conversation (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, ticket_id varchar(128) NOT NULL,
      channel varchar(24) NOT NULL, status varchar(32) NOT NULL DEFAULT 'PENDING_HUMAN_REVIEW',
      idempotency_key varchar(255) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE support_message (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, ticket_id varchar(128) NOT NULL,
      visibility varchar(24) NOT NULL DEFAULT 'CUSTOMER_VISIBLE', approval_status varchar(24) NOT NULL DEFAULT 'PENDING_REVIEW',
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE support_sla_instance (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, ticket_id varchar(128) NOT NULL,
      state varchar(24) NOT NULL DEFAULT 'NOT_STARTED', first_response_target_minutes bigint NOT NULL DEFAULT 0,
      resolution_target_minutes bigint NOT NULL DEFAULT 0, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE support_escalation (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, ticket_id varchar(128) NOT NULL,
      escalation_type varchar(32) NOT NULL, state varchar(24) NOT NULL DEFAULT 'OPEN', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    for index, table, columns in (
        ("ix_support_ticket_scope", "support_ticket", "tenant_id,status"),
        ("ix_support_conversation_scope", "support_conversation", "tenant_id,ticket_id"),
        ("ix_support_message_scope", "support_message", "tenant_id,ticket_id"),
        ("ix_support_sla_scope", "support_sla_instance", "tenant_id,ticket_id,state"),
        ("ix_support_escalation_scope", "support_escalation", "tenant_id,ticket_id,state"),
    ):
        op.execute(f"CREATE INDEX {index} ON {table} ({columns})")


def downgrade() -> None:
    for index, table in (
        ("ix_support_escalation_scope", "support_escalation"),
        ("ix_support_sla_scope", "support_sla_instance"),
        ("ix_support_message_scope", "support_message"),
        ("ix_support_conversation_scope", "support_conversation"),
        ("ix_support_ticket_scope", "support_ticket"),
    ):
        op.drop_index(index, table_name=table)
    for table in ("support_escalation", "support_sla_instance", "support_message", "support_conversation", "support_ticket"):
        op.drop_table(table)
