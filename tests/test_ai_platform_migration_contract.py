from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_ai_foundation_migrations_are_linear_and_define_required_tables():
    foundation = (ROOT / "migrations/versions/0032_ai_platform_foundation.py").read_text()
    registries = (ROOT / "migrations/versions/0033_ai_registries_lead_intelligence.py").read_text()
    assert "revision = \"0032_ai_platform_foundation\"" in foundation
    assert "down_revision = \"0031_social_provider_callbacks\"" in foundation
    assert "request_hash" in foundation
    for table in ("ai_job", "ai_job_event", "ai_job_attempt"):
        assert f"CREATE TABLE {table}" in foundation
    assert "revision = \"0033_ai_registries_lead_intelligence\"" in registries
    assert "down_revision = \"0032_ai_platform_foundation\"" in registries
    for table in (
        "ai_prompt",
        "ai_prompt_version",
        "ai_model",
        "ai_model_policy",
        "ai_approval",
        "ai_output_schema",
        "lead_search",
        "lead_intelligence_record",
        "ai_reconciliation",
    ):
        assert f"CREATE TABLE {table}" in registries


def test_qwen_registry_migration_is_after_lead_intelligence_foundation():
    registry = (ROOT / "migrations/versions/0034_qwen_staging_registry.py").read_text()
    assert "revision = \"0034_qwen_staging_registry\"" in registry
    assert "down_revision = \"0033_ai_registries_lead_intelligence\"" in registry
    for code in ("qwen-primary", "qwen-lead-intelligence-staging", "lead-normalization-v1", "lead-score-v1", "lead-duplicate-review-v1"):
        assert code in registry


def test_human_approval_import_migration_is_linear_and_complete():
    migration = (ROOT / "migrations/versions/0035_human_approval_odoo_import.py").read_text()
    assert "revision = \"0035_human_approval_odoo_import\"" in migration
    assert "down_revision = \"0034_qwen_staging_registry\"" in migration
    for table in ("lead_review", "lead_review_event", "lead_approval_policy", "odoo_import_batch", "odoo_import_item", "odoo_import_attempt", "odoo_import_reconciliation"):
        assert f"CREATE TABLE {table}" in migration


def test_vicidial_assignment_migration_is_linear_and_complete():
    migration = (ROOT / "migrations/versions/0036_vicidial_assignment_foundation.py").read_text()
    assert "revision = \"0036_vicidial_assignment_foundation\"" in migration
    assert "down_revision = \"0035_human_approval_odoo_import\"" in migration
    for table in ("vicidial_assignment_policy", "vicidial_assignment_batch", "vicidial_assignment_item", "vicidial_assignment_attempt", "vicidial_assignment_reconciliation"):
        assert f"CREATE TABLE {table}" in migration
