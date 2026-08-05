from pathlib import Path


MIGRATION = Path("migrations/versions/0034_wave2_event_control_governance.py")


def test_wave2_backfills_all_control_plane_tables_before_not_null():
    text = MIGRATION.read_text()
    assert 'revision = "0034_wave2_event_governance"' in text
    assert 'down_revision = "0033_wave1_identity_governance"' in text
    for table in (
        "enterprise_event",
        "enterprise_event_replay",
        "enterprise_event_subscription",
        "enterprise_event_delivery",
    ):
        assert f"UPDATE {table}" in text
        assert f'_require_common_columns("{table}")' in text
        assert text.index(f"UPDATE {table}") < text.index(
            f'_require_common_columns("{table}")'
        )


def test_wave2_preserves_immutability_and_is_reversible():
    text = MIGRATION.read_text()
    assert text.count("DROP TRIGGER enterprise_event_immutable") == 2
    assert text.count("CREATE TRIGGER enterprise_event_immutable") == 2
    assert "ix_enterprise_event_replay_scope_status" in text
    assert "ix_enterprise_event_subscription_scope_enabled" in text
    assert text.count('_drop_common_columns("enterprise_event') == 4
    assert "govern_enterprise_event_insert" in text
    assert "govern_enterprise_replay_insert" in text
    assert "govern_enterprise_subscription_insert" in text
    assert "govern_enterprise_delivery_insert" in text
    assert "govern_enterprise_control_update" in text
