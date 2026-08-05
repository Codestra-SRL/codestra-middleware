import json
from pathlib import Path


WORKFLOWS = Path(__file__).parents[1] / "workflows/n8n/ai-platform"


def test_ai_workflow_exports_are_sanitized_and_inactive():
    files = sorted(WORKFLOWS.glob("CDA-AI-*.json"))
    assert len(files) == 9
    forbidden = ("sk-", "refresh_token", "private_key", "password", "access_token")
    for path in files:
        document = json.loads(path.read_text())
        assert document["active"] is False
        serialized = path.read_text().lower()
        assert not any(value in serialized for value in forbidden)
        assert "example.invalid" not in serialized or "synthetic" in serialized

