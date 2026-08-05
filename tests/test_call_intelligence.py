import json
from pathlib import Path

import pytest

from app.core.call_intelligence import CallIntelligenceError, canonical_key, redact_text, transition, validate_analysis, validate_transcript


def test_state_machine_and_identity_are_idempotent():
    assert transition("CALL_COMPLETED", "RECORDING_PENDING") == "RECORDING_PENDING"
    assert canonical_key("tenant", "abc") == "codestra:tenant:call:abc"
    with pytest.raises(CallIntelligenceError):
        transition("COMPLETED", "ANALYZING")


def test_redaction_removes_sensitive_values():
    redacted, events = redact_text("card 4111 1111 1111 1111 password: hunter2")
    assert "4111" not in redacted
    assert "hunter2" not in redacted
    assert len(events) >= 2


def test_transcript_and_analysis_schema_validation():
    validate_transcript({"job_id": "j", "language": "en", "language_confidence": 0.9, "segments": [{"speaker": "AGENT", "text": "hello"}], "model_code": "whisper", "model_version": "1"})
    validate_analysis({"summary": "ok", "customer_sentiment": "NEUTRAL", "agent_sentiment": "NEUTRAL", "callback": {"recommended": False}, "confidence": 0.8})
    with pytest.raises(CallIntelligenceError):
        validate_analysis({"summary": "bad", "customer_sentiment": "INVALID", "agent_sentiment": "NEUTRAL", "callback": {"recommended": False}, "confidence": 0.8})


def test_call_workflows_are_inactive_and_credential_free():
    for path in Path("workflows/n8n/call-intelligence").glob("*.json"):
        data = json.loads(path.read_text())
        assert data["active"] is False
        text = path.read_text().lower()
        assert "password" not in text
        assert "authorization:" not in text
