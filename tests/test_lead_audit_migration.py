from pathlib import Path


MIGRATION = Path("migrations/versions/0043_lead_pipeline_audit.py").read_text()


def test_lead_audit_is_append_only_hash_chained_and_trace_indexed():
    assert "previous_hash char(64)" in MIGRATION
    assert "event_hash char(64) NOT NULL" in MIGRATION
    assert "UNIQUE(tenant_id, sequence)" in MIGRATION
    assert "deny_lead_pipeline_audit_mutation" in MIGRATION
    assert "BEFORE UPDATE" in MIGRATION
    assert "BEFORE DELETE" in MIGRATION
    assert "tenant_id,correlation_id,sequence" in MIGRATION
