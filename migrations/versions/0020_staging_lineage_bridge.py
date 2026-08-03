"""Join the deployed staging lineage without discarding its acknowledgement data.

Revision ID: 0020_staging_lineage_bridge
Revises: 0020_outbox_delivery_receipts

The deployed staging lineage created ``n8n_acknowledgement`` before the
provider-neutral transport lineage introduced a different table with that
name.  Preserve the deployed table under an explicit legacy name so the two
lineages can be joined and migrated normally.
"""

from alembic import op


revision = "0020_staging_lineage_bridge"
down_revision = "0020_outbox_delivery_receipts"
branch_labels = None
depends_on = None

RUNTIME_ROLE = "middleware_app"

READ_WRITE = (
    "campaign_extension_allocation",
    "campaign_object_identity",
)
READ_INSERT = (
    "campaign_search_alias",
    "campaign_activation_audit",
)
READ_UPDATE = (
    "campaign_registry",
    "campaign_feature_gate",
)


def _restore_staging_runtime_grants() -> None:
    statements = [
        f"GRANT SELECT, INSERT, UPDATE ON TABLE {table} TO {RUNTIME_ROLE};"
        for table in READ_WRITE
    ]
    statements.extend(
        f"GRANT SELECT, INSERT ON TABLE {table} TO {RUNTIME_ROLE};"
        for table in READ_INSERT
    )
    statements.extend(
        f"GRANT SELECT, UPDATE ON TABLE {table} TO {RUNTIME_ROLE};"
        for table in READ_UPDATE
    )
    statements.append(
        "GRANT USAGE, SELECT ON SEQUENCE campaign_identity_global_seq "
        f"TO {RUNTIME_ROLE};"
    )
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN
            {"".join(statements)}
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.rename_table(
        "n8n_acknowledgement",
        "legacy_n8n_acknowledgement_0020",
    )


def downgrade() -> None:
    op.rename_table(
        "legacy_n8n_acknowledgement_0020",
        "n8n_acknowledgement",
    )
    # The candidate 0020 runtime-grant revision is downgraded while returning
    # to the deployed staging head. Re-establish the grants owned by deployed
    # revision 0018 so the restored 0020 state is privilege-equivalent.
    _restore_staging_runtime_grants()
