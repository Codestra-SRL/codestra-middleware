"""Governed memory and knowledge metadata foundation."""
from alembic import op

revision = "0058_ai_memory_knowledge"
down_revision = "0057_ai_workforce_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE memory_record (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      employee_id varchar(128) NOT NULL DEFAULT '', memory_type varchar(40) NOT NULL,
      memory_scope varchar(32) NOT NULL, classification varchar(24) NOT NULL DEFAULT 'INTERNAL',
      state varchar(32) NOT NULL DEFAULT 'CAPTURED', source_id varchar(128) NOT NULL,
      source_version varchar(64) NOT NULL, expires_at timestamptz NULL, legal_hold boolean NOT NULL DEFAULT false,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("""CREATE TABLE knowledge_source (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      source_type varchar(40) NOT NULL, classification varchar(24) NOT NULL DEFAULT 'INTERNAL',
      source_uri_reference varchar(255) NOT NULL DEFAULT '', version varchar(64) NOT NULL,
      checksum varchar(128) NOT NULL, publication_state varchar(24) NOT NULL DEFAULT 'DRAFT',
      indexing_state varchar(24) NOT NULL DEFAULT 'PENDING', expires_at timestamptz NULL,
      legal_hold boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (tenant_id, workspace_id, source_uri_reference, version)
    )""")
    op.execute("""CREATE TABLE memory_retrieval_request (
      id uuid PRIMARY KEY, tenant_id varchar(128) NOT NULL, workspace_id varchar(128) NOT NULL,
      employee_id varchar(128) NOT NULL, requested_scope varchar(32) NOT NULL,
      authorization_decision varchar(24) NOT NULL DEFAULT 'DENIED', trace_id varchar(128) NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    )""")
    op.execute("CREATE INDEX ix_memory_record_scope ON memory_record(tenant_id,workspace_id,state)")
    op.execute("CREATE INDEX ix_knowledge_source_scope ON knowledge_source(tenant_id,workspace_id,publication_state,indexing_state)")
    op.execute("CREATE INDEX ix_memory_retrieval_scope ON memory_retrieval_request(tenant_id,workspace_id,employee_id)")


def downgrade() -> None:
    op.drop_index("ix_memory_retrieval_scope", table_name="memory_retrieval_request")
    op.drop_index("ix_knowledge_source_scope", table_name="knowledge_source")
    op.drop_index("ix_memory_record_scope", table_name="memory_record")
    op.drop_table("memory_retrieval_request")
    op.drop_table("knowledge_source")
    op.drop_table("memory_record")
