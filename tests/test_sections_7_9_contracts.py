import hashlib
import hmac

from app.core.commercial_platform import ProvisioningRequest, provisioning_is_new
from app.core.data_factory import IngestionContext, lineage_is_traceable, quality_outcome, resolve_entity, validate_ingestion
from app.core.integration_platform import retryable_error, safe_provider_url, verify_webhook


def test_data_factory_contracts_are_scoped_and_traceable():
    context = IngestionContext("odoo", "tenant-a", "workspace-a", "v1", "ingest-1234", "sha256:abc")
    assert validate_ingestion(context) == (True, "VALID")
    assert quality_outcome(required_fields_present=True, valid_values=True) == "PASS"
    assert resolve_entity(exact_identifier=True, similarity=0.1) == "EXACT_MATCH"
    assert lineage_is_traceable(source_reference="s", ingestion_run="r", product_reference="p")


def test_integration_webhooks_and_ssrf_guards_fail_closed():
    body = b'{"event":"ok"}'
    signature = hmac.new(b"secret", b"1700000000." + body, hashlib.sha256).hexdigest()
    assert verify_webhook(body=body, signature=signature, secret=b"secret", timestamp=1700000000, now=1700000000) == (True, "VALID")
    assert verify_webhook(body=body, signature="bad", secret=b"secret", timestamp=1700000000, now=1700000000)[0] is False
    assert safe_provider_url("https://provider.example/api")
    assert not safe_provider_url("http://127.0.0.1")
    assert retryable_error(status_code=503, attempt=0, max_attempts=3)


def test_provisioning_is_idempotency_scoped():
    request = ProvisioningRequest("tenant-a", "workspace-a", "sub-a", "prov-1234")
    assert provisioning_is_new(existing_key=None, request=request)
    assert not provisioning_is_new(existing_key="tenant-a:workspace-a:sub-a:prov-1234", request=request)
