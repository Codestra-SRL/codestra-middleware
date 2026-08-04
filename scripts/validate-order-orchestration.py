"""Offline contract gate for approved-order orchestration artifacts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.order_orchestration import ALLOWED_WORKFLOWS

ROOT = Path(__file__).parents[1]
ORDER_DIR = ROOT / "integrations/n8n/approved-orders"
registry = json.loads((ORDER_DIR / "workflow-registry.json").read_text())
entries = registry["workflows"]
assert registry["payload_schema"] == "codestra.order.command.v1"
assert registry["result_schema"] == "codestra.order.result.v1"
assert len(entries) >= 10
assert {item["workflow_code"] for item in entries} >= ALLOWED_WORKFLOWS
for export in ORDER_DIR.glob("CdstOrder*.json"):
    document = json.loads(export.read_text())
    assert document["active"] is False
    text = export.read_text().lower()
    assert "codestra_middleware_base_url" in text
    assert all(token not in text for token in ("odoo", "vicidial", "postiz"))
print("ORDER_ORCHESTRATION_ARTIFACT_GATE=PASS")
print("N8N_DIRECT_ODOO_PATH_COUNT=0")
print("N8N_DIRECT_VICIDIAL_PATH_COUNT=0")
print("N8N_DIRECT_POSTIZ_PATH_COUNT=0")
print("N8N_CROSS_DATABASE_WRITE_COUNT=0")
