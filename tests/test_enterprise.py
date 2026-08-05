from app.core.enterprise import (
    BackupEvidence,
    DataAccess,
    IdentityAssertion,
    WebhookDecision,
    accept_webhook,
    authorize_data_access,
    validate_backup,
    validate_identity,
)


def test_identity_requires_validated_nonce_and_no_replay():
    assert validate_identity(IdentityAssertion("tenant-a", "user-a", "issuer", "audience", True)) is True
    assert validate_identity(IdentityAssertion("tenant-a", "user-a", "issuer", "audience", True, True)) is False


def test_webhooks_require_signature_replay_protection_and_idempotency():
    assert accept_webhook(WebhookDecision("tenant-a", True, False, "evt-1")) is True
    assert accept_webhook(WebhookDecision("tenant-a", False, False, "evt-1")) is False


def test_data_access_is_row_tenant_scoped():
    assert authorize_data_access(DataAccess("tenant-a", "tenant-a", True)) is True
    assert authorize_data_access(DataAccess("tenant-a", "tenant-b", True)) is False


def test_backup_requires_encryption_off_server_checksum_and_restore():
    assert validate_backup(BackupEvidence("middleware", True, True, True, True)) is True
    assert validate_backup(BackupEvidence("middleware", False, True, True, True)) is False
