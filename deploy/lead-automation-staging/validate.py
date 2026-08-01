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
DOCKERFILE = ROOT.parents[1] / "Dockerfile"
MIDDLEWARE_MATRIX = (
    ROOT / "security" / "scans" / "middleware-vulnerability-remediation-matrix.csv"
)

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
expected_grants = (
    "secrets: [middleware_postgres_password]",
    "secrets: [odoo_postgres_password]",
    "secrets: [redis_password]",
    "secrets: [middleware_database_url]",
    "secrets: [middleware_database_url, redis_url, lead_automation_hmac]",
    "secrets: [odoo_postgres_password, lead_automation_hmac]",
    "- source: n8n_encryption_key",
)
for grant in expected_grants:
    assert grant in compose
top_level_secrets = compose.split("\nsecrets:\n", 1)[1]
assert not re.search(r"(?m)^\s+(uid|gid|mode):", top_level_secrets)
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

dockerfile = DOCKERFILE.read_text()
for label in (
    "org.opencontainers.image.source",
    "org.opencontainers.image.revision",
    "org.opencontainers.image.created",
    "org.opencontainers.image.version",
):
    assert dockerfile.count(label) == 2, f"missing builder/runtime OCI label: {label}"
matrix_lines = MIDDLEWARE_MATRIX.read_text().splitlines()
assert len(matrix_lines) == 11, "expected header plus ten Middleware findings"
print("lead automation staging preparation gates: PASS")
print("COMPOSE_SECRET_GRANT_GATE=PASS")
print("MIDDLEWARE_OCI_LABEL_SOURCE_GATE=PASS")
print("MIDDLEWARE_VULNERABILITY_MATRIX_GATE=PASS")
