from pathlib import Path


MIGRATION = Path("migrations/versions/0033_wave1_identity_governance.py")


def test_wave1_is_additive_and_backfills_before_not_null():
    text = MIGRATION.read_text()
    assert 'revision = "0033_wave1_identity_governance"' in text
    assert 'down_revision = "0032_enterprise_core_completion"' in text
    assert "UPDATE iam_api_key" in text
    assert "UPDATE iam_access_review_item item" in text
    assert text.index("UPDATE iam_api_key") < text.index(
        'op.alter_column("iam_api_key", "updated_at", nullable=False)'
    )
    assert text.index("UPDATE iam_access_review_item item") < text.index(
        'op.alter_column("iam_access_review_item", column, nullable=False)'
    )


def test_wave1_enforces_scope_version_and_reversible_columns():
    text = MIGRATION.read_text()
    assert "fk_iam_review_item_workspace_scope" in text
    assert "ck_iam_access_review_item_version" in text
    assert "ix_iam_access_review_item_scope" in text
    assert text.count('op.drop_column("iam_access_review_item", column)') == 1
