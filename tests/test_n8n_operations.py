from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException, Response

from app.api.v1 import n8n_operations
from app import main
from app.entrypoints import runtime
from app.core.n8n_runtime import ExecutionStatus
from app.db.models import AuditEvent, IdempotencyRecord, N8nRuntimeExecution

OPERATION_ID = UUID("11111111-1111-4111-8111-111111111111")


def _execution(state: ExecutionStatus = ExecutionStatus.PENDING) -> N8nRuntimeExecution:
    now = datetime.now(UTC)
    return N8nRuntimeExecution(
        execution_id=OPERATION_ID,
        tenant_id="tenant-a",
        event_id="TEST_SYN_EVENT",
        event_type="test.synthetic.requested",
        source_event_id="TEST_SYN_SOURCE",
        workflow_code="TEST_SYN_ROUTER",
        workflow_version="1",
        correlation_id="correlation-a",
        causation_id="causation-a",
        trace_id="0123456789abcdef0123456789abcdef",
        idempotency_key_hash="a" * 64,
        payload_hash="b" * 64,
        payload_json={"synthetic": True},
        status=state,
        attempt_count=0,
        timeout_at=now + timedelta(minutes=5),
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def authenticated(monkeypatch):
    def validate(_self, _token):
        return {
            "azp": "codestra-n8n-production",
            "scope": "n8n.operations.read n8n.operations.cancel n8n.operations.reconcile",
            "environment": "production",
            "tenant_id": "tenant-a",
        }

    monkeypatch.setattr(n8n_operations.KeycloakValidator, "validate", validate)
    monkeypatch.setattr(n8n_operations.settings, "n8n_service_issuer", "https://issuer.test")
    monkeypatch.setattr(n8n_operations.settings, "n8n_service_jwks_url", "https://issuer.test/jwks")


def test_openapi_contains_exact_three_compatibility_paths():
    app = FastAPI()
    app.include_router(n8n_operations.router)
    paths = app.openapi()["paths"]
    assert "get" in paths["/v1/integrations/n8n/operations"]
    assert "post" in paths["/v1/integrations/n8n/operations/{operation_id}/cancel"]
    assert "post" in paths["/v1/integrations/n8n/operations/{operation_id}/reconcile"]
    cancel_headers = {
        item["name"]
        for item in paths["/v1/integrations/n8n/operations/{operation_id}/cancel"]["post"]["parameters"]
        if item["in"] == "header" and item["required"]
    }
    assert {
        "Authorization",
        "X-Tenant-ID",
        "X-Correlation-ID",
        "Idempotency-Key",
    }.issubset(cancel_headers)


def test_n8n_operation_routes_use_dedicated_jwt_not_shared_bearer_secret():
    paths = (
        "/v1/integrations/n8n/operations",
        f"/v1/integrations/n8n/operations/{OPERATION_ID}/cancel",
        f"/v1/integrations/n8n/operations/{OPERATION_ID}/reconcile",
    )
    for path in paths:
        assert main.N8N_OPERATION_JWT_PATH.fullmatch(path)
        assert runtime.N8N_OPERATION_JWT_PATH.fullmatch(path)
    assert not main.N8N_OPERATION_JWT_PATH.fullmatch(
        "/v1/integrations/n8n/operations/not-a-uuid/cancel"
    )


def test_authentication_rejects_cross_tenant_claim(authenticated):
    with pytest.raises(HTTPException) as denied:
        n8n_operations._authenticate(
            "Bearer test-token", "tenant-b", "n8n.operations.read"
        )
    assert denied.value.status_code == 403


@pytest.mark.asyncio
async def test_cancel_is_durable_idempotent_and_audited(authenticated):
    operation = _execution()
    db = AsyncMock()
    db.add = MagicMock()
    db.scalar.return_value = None
    db.get.return_value = operation
    response = Response()
    result = await n8n_operations.cancel_operation(
        operation_id=OPERATION_ID,
        response=response,
        authorization="Bearer test-token",
        tenant_id="tenant-a",
        correlation_id="correlation-request",
        idempotency_key="idempotency-key-cancel-0001",
        db=db,
    )
    assert result["state"] == ExecutionStatus.CANCELLED
    assert operation.status == ExecutionStatus.CANCELLED
    assert operation.completed_at is not None
    assert any(isinstance(call.args[0], IdempotencyRecord) for call in db.add.call_args_list)
    assert any(isinstance(call.args[0], AuditEvent) for call in db.add.call_args_list)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_refuses_running_operation_without_downstream_confirmation(
    authenticated,
):
    db = AsyncMock()
    db.add = MagicMock()
    db.scalar.return_value = None
    db.get.return_value = _execution(ExecutionStatus.RUNNING)
    with pytest.raises(HTTPException) as conflict:
        await n8n_operations.cancel_operation(
            operation_id=OPERATION_ID,
            response=Response(),
            authorization="Bearer test-token",
            tenant_id="tenant-a",
            correlation_id="correlation-request",
            idempotency_key="idempotency-key-cancel-0002",
            db=db,
        )
    assert conflict.value.status_code == 409
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_records_request_without_blind_terminal_retry(authenticated):
    db = AsyncMock()
    db.add = MagicMock()
    db.scalar.return_value = None
    db.get.return_value = _execution(ExecutionStatus.DEAD_LETTER)
    with pytest.raises(HTTPException) as conflict:
        await n8n_operations.reconcile_operation(
            operation_id=OPERATION_ID,
            response=Response(),
            authorization="Bearer test-token",
            tenant_id="tenant-a",
            correlation_id="correlation-request",
            idempotency_key="idempotency-key-reconcile-0001",
            db=db,
        )
    assert conflict.value.status_code == 409
    assert "downstream read-back" in conflict.value.detail
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_pending_operation_creates_durable_control_evidence(authenticated):
    db = AsyncMock()
    db.add = MagicMock()
    db.scalar.return_value = None
    db.get.return_value = _execution()
    result = await n8n_operations.reconcile_operation(
        operation_id=OPERATION_ID,
        response=Response(),
        authorization="Bearer test-token",
        tenant_id="tenant-a",
        correlation_id="correlation-request",
        idempotency_key="idempotency-key-reconcile-0002",
        db=db,
    )
    assert result["reconciliation_state"] == "recorded"
    assert any(isinstance(call.args[0], IdempotencyRecord) for call in db.add.call_args_list)
    assert any(isinstance(call.args[0], AuditEvent) for call in db.add.call_args_list)
    db.commit.assert_awaited_once()
