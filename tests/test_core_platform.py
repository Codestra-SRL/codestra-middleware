from app.core.middleware_contracts import ScopeContext, command_allowed, event_allowed, valid_idempotency, valid_scope


def test_core_scope_and_idempotency_are_fail_closed():
    assert valid_scope(ScopeContext("t", "w", "u", "c", "trace"))
    assert not valid_scope(ScopeContext("", "w", "u", "c", "trace"))
    assert valid_idempotency("idempotency-123")
    assert not valid_idempotency("")


def test_mutations_and_events_are_disabled_by_default():
    assert command_allowed(mutations_enabled=False) == (False, "CORE_MUTATIONS_DISABLED")
    assert event_allowed(event_ingestion_enabled=False) == (False, "CORE_EVENT_INGESTION_DISABLED")
    assert command_allowed(mutations_enabled=True, state="BROKEN")[0] is False
