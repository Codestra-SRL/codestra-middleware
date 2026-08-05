"""Fail-closed contracts for the enterprise foundation and middleware buses."""

from dataclasses import dataclass

CORE_COMMAND_STATES = frozenset({"RECEIVED", "VALIDATED", "AUTHORIZED", "QUEUED", "SUCCEEDED", "FAILED", "CANCELLED"})
CORE_EVENT_STATES = frozenset({"RECEIVED", "PUBLISHED", "REPLAYABLE", "REJECTED"})


@dataclass(frozen=True)
class ScopeContext:
    tenant_id: str
    workspace_id: str
    actor_id: str
    correlation_id: str
    trace_id: str


def valid_scope(context: ScopeContext) -> bool:
    return all((context.tenant_id, context.workspace_id, context.actor_id, context.correlation_id, context.trace_id))


def valid_idempotency(key: str | None) -> bool:
    return bool(key and 8 <= len(key) <= 255)


def command_allowed(*, mutations_enabled: bool, state: str = "RECEIVED") -> tuple[bool, str]:
    if state not in CORE_COMMAND_STATES:
        return False, "INVALID_COMMAND_STATE"
    if not mutations_enabled:
        return False, "CORE_MUTATIONS_DISABLED"
    return True, "VALID"


def event_allowed(*, event_ingestion_enabled: bool, state: str = "RECEIVED") -> tuple[bool, str]:
    if state not in CORE_EVENT_STATES:
        return False, "INVALID_EVENT_STATE"
    if not event_ingestion_enabled:
        return False, "CORE_EVENT_INGESTION_DISABLED"
    return True, "VALID"
