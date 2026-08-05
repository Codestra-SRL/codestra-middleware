from pathlib import Path


MIGRATION = Path("migrations/versions/0030_enterprise_identity_core.py")


def test_enterprise_identity_migration_has_governed_columns():
    text = MIGRATION.read_text()
    for column in (
        "tenant_id",
        "workspace_id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "deleted_at",
        "version",
        "audit_id",
    ):
        assert f'"{column}"' in text


def test_enterprise_identity_scope_constraints_are_explicit():
    text = MIGRATION.read_text()
    assert "uq_iam_principal_scope_subject" in text
    assert "uq_iam_role_binding_scope" in text
    assert "iam_workspace.tenant_id" in text
    assert "ondelete=\"RESTRICT\"" in text


def test_session_storage_contains_hashes_not_tokens():
    text = MIGRATION.read_text()
    assert "provider_session_id_hash" in text
    assert "device_fingerprint_hash" in text
    assert "refresh_token" not in text
    assert "access_token" not in text


def test_migration_is_reversible_in_dependency_order():
    text = MIGRATION.read_text()
    positions = [text.index(f'op.drop_table("{table}")') for table in (
        "iam_session", "iam_role_binding", "iam_principal", "iam_workspace", "iam_tenant"
    )]
    assert positions == sorted(positions)
