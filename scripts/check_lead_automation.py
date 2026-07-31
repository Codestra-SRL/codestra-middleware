import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
schemas = ROOT / "schemas/lead-automation"
manifest = json.loads((schemas / "SHA256SUMS.json").read_text())
assert manifest["contract_version"] == "1.0" and manifest["schema_count"] == 13
for name, digest in manifest["schemas"].items():
    path = schemas / name
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    value = json.loads(path.read_text())
    assert value["type"] == "object" and value["additionalProperties"] is False
forbidden = (
    "telephone_number",
    "phone_number",
    "email_address",
    "customer_name",
    "raw_provider_token",
    "recording_url",
    "object_key",
    "filesystem_path",
    "audio_binary",
    "credential",
)
text = "\n".join(path.read_text().lower() for path in schemas.glob("*.json"))
assert not any(term in text for term in forbidden)
config = (ROOT / "app/core/config.py").read_text()
for setting in (
    "lead_automation_enabled",
    "lead_create_enabled",
    "lead_update_enabled",
    "lead_assignment_enabled",
    "lead_status_change_enabled",
    "lead_callback_create_enabled",
    "n8n_lead_binding_enabled",
    "n8n_result_processing_enabled",
    "odoo_lead_apply_enabled",
):
    assert f"{setting}: bool = False" in config
workflow = json.loads(
    (ROOT / "deploy/n8n/lead-automation/lead-automation-generic-v1.json").read_text()
)
assert (
    workflow["active"] is False and workflow["meta"]["binding_enabled_default"] is False
)
assert all(node.get("disabled") is True for node in workflow["nodes"])
types = {node["type"].lower() for node in workflow["nodes"]}
assert not any(
    any(
        term in item
        for term in ("postgres", "odoo", "email", "sms", "whatsapp", "calendar")
    )
    for item in types
)
assert not any(
    "recording" in path.as_posix().lower()
    for path in [
        ROOT / "app/core/lead_automation.py",
        ROOT / "app/api/v1/lead_automation.py",
    ]
)
print("lead automation source gates: PASS")
