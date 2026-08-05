import json
from pathlib import Path


def test_assignment_exports_are_inactive_and_sanitized():
    files = list((Path(__file__).parents[1] / "workflows/n8n/vicidial-assignment").glob("CDA-AI-*.json"))
    assert len(files) == 8
    for path in files:
        data = json.loads(path.read_text())
        assert data["active"] is False
        text = path.read_text().lower()
        assert "password" not in text and "access_token" not in text and "private_key" not in text

