from pathlib import Path


ROOT = Path(__file__).parents[1]
DEPLOY = ROOT / "deploy" / "recording-storage"


def test_storage_is_digest_pinned_private_and_console_absent():
    text = (DEPLOY / "compose.yaml").read_text()
    assert "image: quay.io/minio/minio@sha256:" in text
    assert '"10.40.0.1:9000:9000"' in text
    assert "9001:9001" not in text
    assert "internal: true" in text
    assert "RECORDING_RETENTION_EXECUTION_ENABLED: \"false\"" in text


def test_storage_security_contract():
    text = (DEPLOY / "compose.yaml").read_text()
    bootstrap = (DEPLOY / "bootstrap-policy.sh").read_text()
    assert "MINIO_KMS_KES_ENDPOINT" in text
    assert "--with-lock" in bootstrap
    assert "version enable" in bootstrap
    assert "GOVERNANCE 365d" in bootstrap
    for identity in (
        "recording-middleware-write",
        "recording-middleware-read",
        "recording-retention-worker",
        "recording-backup-auditor",
    ):
        assert identity in bootstrap
