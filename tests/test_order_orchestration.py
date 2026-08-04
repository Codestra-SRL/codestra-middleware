from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.order_orchestration import (
    Approval,
    OrderEnvelope,
    OrderStatus,
    OrderStore,
    content_hash,
    validate_for_dispatch,
    verify_body_integrity,
)


def envelope(**overrides) -> OrderEnvelope:
    now = datetime.now(timezone.utc)
    values = {
        "schema_version": "codestra.order.command.v1",
        "command_id": "cmd-test-001",
        "event_id": "event-test-001",
        "order_id": "CODESTRA-INTEGRATION-TEST-ORDER-001",
        "order_type": "shipping_order",
        "source_system": "odoo",
        "organization_id": "org-test",
        "customer_reference": "customer-opaque-001",
        "workflow_code": "CDST-ORDER-SHIPPING-V1",
        "approval": {"required": True, "status": "approved", "content_hash": "0" * 64},
        "payload": {"destination_reference": "warehouse-test"},
        "requested_actions": ["create_fulfillment_task"],
        "constraints": {"synthetic": True},
        "idempotency_key": "CODESTRA-INTEGRATION-TEST-IDEMP-001",
        "correlation_id": "corr-test-001",
        "trace_id": "trace-test-001",
        "requested_at": now,
        "expires_at": now + timedelta(minutes=10),
    }
    values.update(overrides)
    order = OrderEnvelope.model_validate(values)
    order.approval = Approval(status="approved", content_hash=content_hash(order))
    return order


def test_order_lifecycle_and_duplicate_suppression():
    store = OrderStore()
    order = envelope()
    first = store.create(order)
    second = store.create(order)
    assert first["status"] == OrderStatus.APPROVAL_REQUIRED.value
    assert second["duplicate"] is True
    assert len(store.orders) == 1


def test_dispatch_rejects_expired_order():
    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    order = envelope(
        requested_at=expired - timedelta(minutes=10),
        expires_at=expired,
    )
    with pytest.raises(HTTPException, match="expired"):
        validate_for_dispatch(order)


def test_dispatch_rejects_unknown_workflow_and_blocked_action():
    unknown = envelope(workflow_code="CUSTOMER_TEXT_SELECTED_WORKFLOW")
    with pytest.raises(HTTPException, match="allowlisted"):
        validate_for_dispatch(unknown)
    blocked = envelope(requested_actions=["send_customer_message"])
    with pytest.raises(HTTPException, match="blocked"):
        validate_for_dispatch(blocked)


def test_n8n_exports_have_only_middleware_urls_and_are_inactive():
    root = Path(__file__).parents[1] / "integrations/n8n/approved-orders"
    exports = list(root.glob("CdstOrder*.json"))
    assert len(exports) == 7
    for export in exports:
        text = export.read_text()
        assert '"active":false' in text
        assert "CODESTRA_MIDDLEWARE_BASE_URL" in text
        assert "odoo.com" not in text.lower()
        assert "vicidial" not in text.lower()
        assert "postiz" not in text.lower()


def test_flags_default_disabled():
    from app.core.config import Settings

    settings = Settings()
    assert settings.order_orchestration_enabled is False
    assert settings.n8n_order_dispatch_enabled is False


def test_modified_body_and_bad_signature_are_rejected(monkeypatch):
    order = envelope()
    from app.core.config import settings
    monkeypatch.setattr(settings, "middleware_secret", "test-secret")
    import hashlib
    import json
    body_hash = hashlib.sha256(json.dumps(order.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with pytest.raises(HTTPException, match="signature invalid"):
        verify_body_integrity(order, "1700000000", "nonce-1", "bad", body_hash)
    with pytest.raises(HTTPException, match="body hash mismatch"):
        verify_body_integrity(order, "1700000000", "nonce-1", "bad", "0" * 64)
