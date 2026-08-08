import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError

from app.core.config import settings
from app.core.n8n_runtime import (
    DispatchRequest,
    ResultContract,
    canonical_bytes,
    retry_delay,
    retryable,
    sha256,
    sign_runtime,
    verify_fresh,
    verify_runtime,
)
from app.core.runtime_redis import (
    RedisCoordinator,
    RedisKeyType,
    TTL_SECONDS,
    runtime_key,
)
from app.workers.n8n_runtime import recover_stale_dispatches


def dispatch_payload(**overrides):
    value = {
        "schema_version": "codestra.n8n.dispatch.v1",
        "tenant_id": "tenant-a",
        "event_id": "TEST_SYN_event-1",
        "event_type": "test.synthetic.requested",
        "source_event_id": "source-1",
        "correlation_id": "correlation-1",
        "causation_id": "causation-1",
        "trace_id": "0123456789abcdef0123456789abcdef",
        "idempotency_key": "fixture-key-0001",
        "payload": {"fixture": True},
    }
    value.update(overrides)
    return value


def result_payload(**overrides):
    value = {
        "schema_version": "codestra.n8n.result.v1",
        "workflow_code": "TEST_SYN_ROUTER",
        "workflow_version": "1",
        "execution_id": "11111111-1111-1111-1111-111111111111",
        "correlation_id": "correlation-1",
        "tenant_id": "tenant-a",
        "status": "completed",
        "occurred_at": datetime.now(UTC).isoformat(),
        "result": {"synthetic": True},
    }
    value.update(overrides)
    return value


def test_strict_dispatch_contract():
    assert DispatchRequest.model_validate(dispatch_payload()).tenant_id == "tenant-a"
    with pytest.raises(ValueError):
        DispatchRequest.model_validate(dispatch_payload(workflow_id="attacker-choice"))


def test_dispatch_payload_is_bounded():
    with pytest.raises(ValueError):
        DispatchRequest.model_validate(
            dispatch_payload(payload={"value": "x" * 131073})
        )


def test_result_contract_version_and_unknown_fields_are_rejected():
    assert ResultContract.model_validate(result_payload()).status == "completed"
    with pytest.raises(ValueError):
        ResultContract.model_validate(result_payload(schema_version="2"))
    with pytest.raises(ValueError):
        ResultContract.model_validate(result_payload(secret="not-accepted"))


def test_signature_binds_all_runtime_dimensions():
    secret = b"x" * 32
    values = dict(
        identity="n8n-staging",
        tenant_id="tenant-a",
        workflow_code="TEST_SYN_ROUTER",
        execution_id="execution-1",
        correlation_id="correlation-1",
        timestamp=str(int(time.time())),
        nonce="nonce-1",
        body_hash="a" * 64,
    )
    signature = sign_runtime(secret=secret, **values)
    verify_runtime(signature, secret, **values)
    for field in values:
        modified = dict(values)
        modified[field] = modified[field] + "-modified"
        with pytest.raises(ValueError):
            verify_runtime(signature, secret, **modified)


def test_timestamp_replay_window():
    verify_fresh(str(int(time.time())))
    with pytest.raises(ValueError):
        verify_fresh(str(int(time.time()) - 301))


@pytest.mark.parametrize("status", [408, 429, 502, 503, 504])
def test_safe_retry_statuses(status):
    assert retryable(status)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_permanent_failure_statuses(status):
    assert not retryable(status)


def test_retry_jitter_is_bounded():
    assert 0 <= retry_delay(1) <= 1
    assert 0 <= retry_delay(8) <= 60
    with pytest.raises(ValueError):
        retry_delay(0)


def test_canonical_hash_is_order_independent():
    assert sha256(canonical_bytes({"a": 1, "b": 2})) == sha256(
        canonical_bytes({"b": 2, "a": 1})
    )


def test_every_redis_runtime_key_has_ttl_and_environment(monkeypatch):
    monkeypatch.setattr(settings, "redis_runtime_environment", "staging")
    assert all(value > 0 for value in TTL_SECONDS.values())
    for kind in RedisKeyType:
        key = runtime_key(kind, "tenant-a", "execution-1")
        assert key.startswith("codestra:staging:")


def test_redis_namespace_rejects_injection(monkeypatch):
    monkeypatch.setattr(settings, "redis_runtime_environment", "staging")
    with pytest.raises(ValueError):
        runtime_key(RedisKeyType.LOCK, "tenant:production:escape")


@pytest.mark.asyncio
async def test_redis_failure_degrades_without_losing_durable_work(monkeypatch):
    monkeypatch.setattr(settings, "redis_runtime_enabled", True)
    client = AsyncMock()
    client.set.side_effect = ConnectionError("unavailable")
    result = await RedisCoordinator(client).reserve(
        RedisKeyType.DEDUPE, "execution-1", "tenant-a", "execution-1"
    )
    assert result.acquired is True
    assert result.degraded is True


@pytest.mark.asyncio
async def test_redis_reservations_always_set_positive_expiry(monkeypatch):
    monkeypatch.setattr(settings, "redis_runtime_enabled", True)
    monkeypatch.setattr(settings, "redis_runtime_environment", "staging")
    client = AsyncMock()
    client.set.return_value = True
    result = await RedisCoordinator(client).reserve(
        RedisKeyType.REPLAY, "execution-1", "tenant-a", "nonce-1"
    )
    assert result.acquired and not result.degraded
    assert client.set.await_args.kwargs["ex"] == TTL_SECONDS[RedisKeyType.REPLAY]
    assert client.set.await_args.kwargs["nx"] is True


@pytest.mark.asyncio
async def test_stale_dispatch_recovery_uses_bounded_lease():
    session = AsyncMock()
    session.execute.return_value.rowcount = 1
    assert await recover_stale_dispatches(session, 60) == 1
    session.commit.assert_awaited_once()
    with pytest.raises(ValueError):
        await recover_stale_dispatches(session, 1)
