from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.v1.interactions import CallbackRequest, DispositionRequest, NotesRequest
from app.entrypoints.integration_api import app

ROOT = Path(__file__).resolve().parents[1]


def test_interaction_api_surface_is_complete():
    methods = {
        (route.path, method)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }
    required = {
        ("/api/v1/interactions/{interaction_id}/notes", "POST"),
        ("/api/v1/interactions/{interaction_id}/disposition", "POST"),
        ("/api/v1/interactions/{interaction_id}/callback", "POST"),
        ("/api/v1/interactions/{interaction_id}/results", "GET"),
    }
    assert required <= methods


def test_migration_defines_durable_result_table_with_idempotency_and_delivery_tracking():
    migration = (
        ROOT / "migrations/versions/0057_interaction_result.py"
    ).read_text()
    assert "CREATE TABLE interaction_result" in migration
    assert "uq_interaction_result_idem" in migration
    assert "delivery_status" in migration
    assert "CHECK (result_type IN ('notes','disposition','callback'))" in migration


def test_disposition_code_must_be_uppercase_shape_not_free_text():
    with pytest.raises(ValidationError):
        DispositionRequest(crm_lead_public_id="9001", disposition_code="not a real code")
    DispositionRequest(crm_lead_public_id="9001", disposition_code="QUALIFIED")


def test_notes_request_rejects_empty_body():
    with pytest.raises(ValidationError):
        NotesRequest(crm_lead_public_id="9001", notes_text="")


def test_notes_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        NotesRequest(crm_lead_public_id="9001", notes_text="ok", extra_field="nope")


def test_callback_request_requires_well_formed_fields():
    with pytest.raises(ValidationError):
        CallbackRequest(crm_lead_public_id="", scheduled_for="2030-01-01T00:00:00Z", timezone="UTC", reason="x")


@pytest.mark.asyncio
async def test_duplicate_idempotency_key_returns_cached_response_without_reinsert():
    """A retried save with the same Idempotency-Key must not create a second row."""
    from app.api.v1 import interactions as mod

    body = NotesRequest(crm_lead_public_id="9001", notes_text="hello")
    fake_request = AsyncMock()
    fake_request.headers = {}
    db = AsyncMock()
    cached_response = {"interaction_result_id": str(uuid4()), "status": "accepted", "correlation_id": "c-1"}
    prior_row = type("Row", (), {"response": cached_response})()

    with patch.object(mod, "authenticate_agent", new=AsyncMock(return_value=_fake_agent())):
        with patch.object(mod.Idem, "check", new=AsyncMock(return_value=(prior_row, "h", "kh"))):
            result = await mod._write(
                db, fake_request, "call-1", "notes", body,
                {"notes_text": "hello"}, "same-key", None,
            )
    assert result == cached_response
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_db_failure_on_commit_raises_and_never_returns_success():
    """The core AGENT-01 contract: a persistence failure must never look like a 202."""
    from fastapi import HTTPException

    from app.api.v1 import interactions as mod

    body = NotesRequest(crm_lead_public_id="9001", notes_text="hello")
    fake_request = AsyncMock()
    fake_request.headers = {}
    db = AsyncMock()
    db.commit.side_effect = RuntimeError("connection lost")

    with patch.object(mod, "authenticate_agent", new=AsyncMock(return_value=_fake_agent())):
        with patch.object(mod.Idem, "check", new=AsyncMock(return_value=(None, "h", "kh"))):
            with pytest.raises(HTTPException) as excinfo:
                await mod._write(
                    db, fake_request, "call-1", "notes", body,
                    {"notes_text": "hello"}, "key-1", None,
                )
    assert excinfo.value.status_code == 500
    db.rollback.assert_called_once()


def _fake_agent():
    from app.core.agent_identity import AgentIdentity

    return AgentIdentity(
        subject="agent-sub-1",
        employee_id="EMP-1",
        odoo_employee_id="EMP-1",
        vicidial_username="agent1",
        role="codestra_agent",
        business_unit_id="BU-1",
        tenant_id="T-1",
    )
