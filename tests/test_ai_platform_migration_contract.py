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
