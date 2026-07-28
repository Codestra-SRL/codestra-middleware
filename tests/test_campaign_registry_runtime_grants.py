from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1]
    / "migrations"
    / "versions"
    / "0018_campaign_registry_runtime_grants.py"
)


def test_runtime_grants_are_scoped_and_fail_closed():
    source = MIGRATION.read_text()

    assert 'RUNTIME_ROLE = "middleware_app"' in source
    assert "IF EXISTS (SELECT 1 FROM pg_roles" in source
    assert '"campaign_registry"' in source
    assert '"campaign_feature_gate"' in source
    assert '"campaign_extension_allocation"' in source
    assert '"campaign_activation_audit"' in source
    assert "GRANT SELECT, UPDATE ON TABLE {table}" in source
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE {table}" in source
    assert "GRANT SELECT, INSERT ON TABLE {table}" in source
    assert "GRANT USAGE, SELECT ON SEQUENCE campaign_identity_global_seq" in source

    upgrade = source.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    for forbidden in ("DELETE", "TRUNCATE", "REFERENCES", "TRIGGER", "CREATE"):
        assert forbidden not in upgrade


def test_downgrade_revokes_access_without_deleting_identity_data():
    source = MIGRATION.read_text()
    downgrade = source.split("def downgrade()", 1)[1]

    assert "REVOKE ALL PRIVILEGES" in downgrade
    for destructive in ("DROP TABLE", "DELETE FROM", "TRUNCATE"):
        assert destructive not in downgrade
