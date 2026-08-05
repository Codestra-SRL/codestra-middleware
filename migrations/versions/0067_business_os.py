"""AI Business Operating System foundation."""
from alembic import op

revision = "0067_business_os"
down_revision = "0066_release_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE business_graph_node (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      node_type varchar(32) NOT NULL, external_reference varchar(255) NOT NULL, classification varchar(24) NOT NULL DEFAULT 'INTERNAL', created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE business_graph_edge (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      source_node_id uuid NOT NULL, target_node_id uuid NOT NULL, relationship varchar(48) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE business_timeline_event (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      event_type varchar(48) NOT NULL, subject_reference varchar(255) NOT NULL, occurred_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE business_command (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      actor_id varchar(128) NOT NULL, action varchar(48) NOT NULL, state varchar(24) NOT NULL DEFAULT 'REQUESTED', idempotency_key varchar(160) NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_business_graph_node_scope ON business_graph_node(tenant_id,workspace_id,node_type)")
    op.execute("CREATE INDEX ix_business_graph_edge_scope ON business_graph_edge(tenant_id,workspace_id,relationship)")
    op.execute("CREATE INDEX ix_business_timeline_scope ON business_timeline_event(tenant_id,workspace_id,occurred_at)")
    op.execute("CREATE INDEX ix_business_command_scope ON business_command(tenant_id,workspace_id,state)")


def downgrade() -> None:
    op.drop_index("ix_business_command_scope", table_name="business_command")
    op.drop_index("ix_business_timeline_scope", table_name="business_timeline_event")
    op.drop_index("ix_business_graph_edge_scope", table_name="business_graph_edge")
    op.drop_index("ix_business_graph_node_scope", table_name="business_graph_node")
    op.drop_table("business_command")
    op.drop_table("business_timeline_event")
    op.drop_table("business_graph_edge")
    op.drop_table("business_graph_node")
