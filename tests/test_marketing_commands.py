from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response

from app.api.v1 import marketing_commands
from app.api.v1.marketing_commands import ActivationCommand, create_campaign_activation
from app.db.models import AuditEvent, EventInbox, IdempotencyRecord, OutboxEvent


class FakeSession:
    def __init__(self, prior=None):
        self.prior = prior
        self.added: list[object] = []
        self.execute = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def scalar(self, _statement):
        return self.prior

    def add(self, value):
        self.added.append(value)


def _command() -> ActivationCommand:
    operation_id = uuid4()
    return ActivationCommand(
        operation_id=operation_id,
        campaign_id=uuid4(),
        expected_version=1,
        tenant_id="tenant-1",
        correlation_id="correlation-1",
    )


@pytest.fixture(autouse=True)
def authenticated_service(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        marketing_commands,
        "_authenticate",
        lambda _authorization, _tenant: {"azp": "marketing-service"},
    )


@pytest.mark.asyncio
async def test_activation_intake_is_atomic_idempotent_and_audited(monkeypatch: pytest.MonkeyPatch):
    command = _command()
    session = FakeSession()
    monkeypatch.setattr(marketing_commands.settings, "marketing_command_intake_enabled", True)
    response = Response()

    result = await create_campaign_activation(
        command,
        response,
        "Bearer synthetic",
        command.tenant_id,
        command.correlation_id,
        str(command.operation_id),
        session,  # type: ignore[arg-type]
    )

    assert result["operation_id"] == str(command.operation_id)
    assert result["state"] == "pending"
    assert response.headers["X-Correlation-ID"] == command.correlation_id
    assert sum(isinstance(item, EventInbox) for item in session.added) == 1
    assert sum(isinstance(item, OutboxEvent) for item in session.added) == 1
    assert sum(isinstance(item, IdempotencyRecord) for item in session.added) == 1
    assert sum(isinstance(item, AuditEvent) for item in session.added) == 1
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_activation_intake_fails_closed_when_disabled(monkeypatch: pytest.MonkeyPatch):
    command = _command()
    session = FakeSession()
    monkeypatch.setattr(marketing_commands.settings, "marketing_command_intake_enabled", False)
    with pytest.raises(HTTPException) as disabled:
        await create_campaign_activation(
            command,
            Response(),
            "Bearer synthetic",
            command.tenant_id,
            command.correlation_id,
            str(command.operation_id),
            session,  # type: ignore[arg-type]
        )
    assert disabled.value.status_code == 503
    assert not session.added
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_activation_replay_returns_durable_response_without_new_side_effects(
    monkeypatch: pytest.MonkeyPatch,
):
    command = _command()
    durable = {
        "operation_id": str(command.operation_id),
        "state": "pending",
        "correlation_id": command.correlation_id,
        "duplicate": False,
    }
    prior = IdempotencyRecord(
        scope=f"marketing-activation:{command.tenant_id}",
        key_hash="unused-by-fake",
        request_hash=marketing_commands._request_hash(command),
        response=durable,
        status_code=202,
    )
    session = FakeSession(prior)
    monkeypatch.setattr(marketing_commands.settings, "marketing_command_intake_enabled", True)
    response = Response()
    result = await create_campaign_activation(
        command,
        response,
        "Bearer synthetic",
        command.tenant_id,
        command.correlation_id,
        str(command.operation_id),
        session,  # type: ignore[arg-type]
    )
    assert response.status_code == 200
    assert result["duplicate"] is True
    assert not session.added
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_activation_rejects_header_body_context_mismatch():
    command = _command()
    with pytest.raises(HTTPException) as denied:
        await create_campaign_activation(
            command,
            Response(),
            "Bearer synthetic",
            "another-tenant",
            command.correlation_id,
            str(command.operation_id),
            FakeSession(),  # type: ignore[arg-type]
        )
    assert denied.value.status_code == 403
