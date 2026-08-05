import json
from pathlib import Path


def test_canary_workflows_are_inactive_and_credential_free():
    root = Path("workflows/n8n/vicidial-canary")
    files = list(root.glob("*.json"))
    assert len(files) >= 6
    for path in files:
        data = json.loads(path.read_text())
        assert data["active"] is False
        text = path.read_text().lower()
        assert "password" not in text
        assert "authorization:" not in text
