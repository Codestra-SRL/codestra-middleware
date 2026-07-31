import json
from pathlib import Path

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]
STORAGE = ROOT / "deploy" / "recording-storage"


def test_contract_and_n8n_inactive_schema():
    contract = json.loads(
        (ROOT / "schemas/recording/recording-contract-v1.json").read_text()
    )
    assert contract["contract_version"] == "1.0"
    workflow = json.loads(
        (STORAGE / "n8n/recording-postprocess-v1.json").read_text()
    )
    assert workflow["active"] is False
    assert workflow["meta"]["binding_enabled_default"] is False
    for action in (
        "email_actions", "sms_actions", "whatsapp_actions", "calendar_actions",
        "appointment_actions", "crm_lead_actions",
    ):
        assert workflow["meta"][action] is False


def test_storage_private_lock_versioning_encryption_and_kms_gate():
    compose = (STORAGE / "compose.yaml").read_text()
    bootstrap = (STORAGE / "bucket-bootstrap/bootstrap.sh").read_text()
    assert "ports:" not in compose
    assert "internal: true" in compose
    assert "@sha256:" in compose
    assert "--with-lock" in bootstrap
    assert "version enable" in bootstrap
    assert "encrypt set sse-s3" in bootstrap
    assert "retention set --default GOVERNANCE" in bootstrap
    assert "PRODUCTION_KMS_PROVIDER" in bootstrap


def test_all_dangerous_switches_are_disabled():
    settings = Settings()
    assert settings.retention_worker_enabled is True
    assert settings.retention_delete_enabled is False
    assert settings.export_upload_enabled is False
    assert settings.odoo_recording_write_enabled is False
    assert settings.n8n_recording_workflow_enabled is False
    assert settings.recording_playback_url_ttl_seconds <= 120


def test_no_customer_identifiers_or_public_recording_urls():
    relevant = [
        *ROOT.glob("app/recording/*.py"),
        *ROOT.glob("deploy/recording-storage/**/*"),
    ]
    text = "\n".join(
        p.read_text(errors="ignore") for p in relevant if p.is_file()
    ).lower()
    assert "telephone_number" not in text
    assert "customer_name" not in text
    assert "public-read" not in text
