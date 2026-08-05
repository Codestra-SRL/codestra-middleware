import pytest
from fastapi import HTTPException

from app.api.v1.marketplace import require_marketplace
from app.core.marketplace import ManifestError, manifest_digest, transition, validate_manifest


def valid_manifest():
    return {"plugin_code": "official.test", "publisher_id": "codestra", "plugin_type": "AI_SCHEMA_PACKAGE", "version": "1.0.0", "requested_capabilities": ["ai.prompt.use"], "package_digest": "sha256:" + "a" * 64, "signature": "trusted-signature-value"}


def test_signed_manifest_contract_and_digest():
    manifest = validate_manifest(valid_manifest())
    assert manifest.plugin_code == "official.test"
    assert manifest_digest(valid_manifest()).startswith("sha256:")


def test_unsigned_or_wildcard_manifest_rejected():
    payload = valid_manifest()
    payload["signature"] = "short"
    with pytest.raises(ManifestError):
        validate_manifest(payload)
    payload = valid_manifest()
    payload["requested_capabilities"] = ["*"]
    with pytest.raises(ManifestError):
        validate_manifest(payload)


def test_plugin_lifecycle_is_fail_closed():
    assert transition("DRAFT", "VALIDATING") == "VALIDATING"
    with pytest.raises(ManifestError):
        transition("DRAFT", "ACTIVE")


def test_marketplace_role_guard_rejects_unprivileged_role():
    with pytest.raises(HTTPException) as exc:
        require_marketplace("CUSTOMER_READ_ONLY")
    assert exc.value.status_code == 403
