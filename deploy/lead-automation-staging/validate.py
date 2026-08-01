from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent
ENV = ROOT / "staging.env.example"
COMPOSE = ROOT / "compose.yaml"
FIXTURES = ROOT / "synthetic-fixtures.json"
SECURITY_DECISION = ROOT / "security" / "image-security-decision.json"

required_false = {
    "LEAD_AUTOMATION_ENABLED",
    "LEAD_CREATE_ENABLED",
    "LEAD_UPDATE_ENABLED",
    "LEAD_ASSIGNMENT_ENABLED",
    "LEAD_STATUS_CHANGE_ENABLED",
    "LEAD_CALLBACK_CREATE_ENABLED",
    "N8N_LEAD_BINDING_ENABLED",
    "N8N_RESULT_PROCESSING_ENABLED",
    "ODOO_LEAD_APPLY_ENABLED",
    "EMAIL_DELIVERY_ENABLED",
    "SMS_DELIVERY_ENABLED",
    "WHATSAPP_DELIVERY_ENABLED",
    "CALENDAR_SYNC_ENABLED",
    "APPOINTMENT_AUTOMATION_ENABLED",
    "N8N_WORKFLOW_ACTIVE_DEFAULT",
    "N8N_BINDING_ENABLED_DEFAULT",
}
allowed = required_false | {
    "COMPOSE_PROJECT_NAME",
    "MIDDLEWARE_IMAGE",
    "POSTGRES_IMAGE",
    "REDIS_IMAGE",
    "ODOO_IMAGE",
    "N8N_IMAGE",
    "ODOO_ADDONS_PATH",
    "STAGING_SECRET_DIRECTORY",
    "STAGING_BACKUP_DIRECTORY",
}
values: dict[str, str] = {}
for raw in ENV.read_text().splitlines():
    if not raw or raw.startswith("#"):
        continue
    key, value = raw.split("=", 1)
    assert key in allowed, f"unknown staging variable: {key}"
    values[key] = value
assert required_false <= values.keys()
assert all(values[key] == "false" for key in required_false)
assert set(values) == allowed

compose = COMPOSE.read_text()
assert "ports:" not in compose
assert "internal: true" in compose
assert "codestra-lead-staging-network" in compose
assert "restart: \"no\"" in compose
assert "profiles: [deployment]" in compose
assert "profiles: [operations]" in compose
assert not re.search(
    r"(?m)^[ \t]+[A-Z0-9_]*(PASSWORD|SECRET|TOKEN):[ \t]+[^/$\s{]", compose
)
for image in ("POSTGRES_IMAGE", "REDIS_IMAGE", "ODOO_IMAGE", "N8N_IMAGE"):
    assert "@sha256:" in values[image]

subprocess.run(["python3", str(ROOT / "security_decision.py")], check=True)
decision = json.loads(SECURITY_DECISION.read_text())
counts = json.loads((ROOT / "security" / "vulnerability-counts.json").read_text())
assert counts["redis"]["digest"] in values["REDIS_IMAGE"]
assert counts["n8n"]["digest"] in values["N8N_IMAGE"]
assert counts["postgres"]["digest"] in values["POSTGRES_IMAGE"]
assert "n8n_data:/home/node/.n8n" in compose
assert "/home/node/.n8n:" not in "\n".join(line for line in compose.splitlines() if "tmpfs" in line)
assert "n8n_cache:/home/node/.cache" not in compose

fixtures = json.loads(FIXTURES.read_text())
serialized = json.dumps(fixtures).lower()
for prohibited in ("@", "phone", "recording", "presigned", "object_storage", "production"):
    assert prohibited not in serialized
assert fixtures["environment"] == "staging"
print("lead automation staging preparation gates: PASS")
