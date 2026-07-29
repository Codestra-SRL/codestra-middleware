"""Fail-closed validation for the shared event gateway."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from app.core.automation import canonical_hash
from app.schemas.generic_events import GenericEvent


class GenericEventError(ValueError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class EventSchema:
    event_type: str
    schema_version: str
    producer_service: str
    required_payload_fields: frozenset[str] = frozenset()


class SchemaRegistry:
    """Small deterministic registry boundary used by the HTTP gateway.

    The active deployment may replace this with the database-backed resolver;
    no request is accepted through an implicit ``allow all`` fallback.
    """

    def __init__(self, schemas: tuple[EventSchema, ...] = ()) -> None:
        self._schemas = {
            (item.event_type, item.schema_version, item.producer_service): item
            for item in schemas
        }

    def resolve(
        self, *, event_type: str, schema_version: str, producer_service: str
    ) -> EventSchema:
        matches = [
            item
            for (candidate_type, candidate_version, candidate_producer), item in self._schemas.items()
            if candidate_type == event_type
            and candidate_version == schema_version
            and candidate_producer == producer_service
        ]
        if len(matches) != 1:
            code = "EVENT_TYPE_UNSUPPORTED" if not matches else "SCHEMA_BINDING_AMBIGUOUS"
            status = 422 if not matches else 503
            raise GenericEventError(code, "event schema is not currently accepted", status)
        return matches[0]


def _digest(value: str) -> str:
    return value.removeprefix("sha256:")


def validate_generic_event(
    raw: Mapping[str, Any],
    *,
    registry: SchemaRegistry,
    expected_environment: str,
    now: datetime | None = None,
    max_lifetime_seconds: int = 300,
) -> GenericEvent:
    try:
        event = GenericEvent.model_validate(raw)
    except Exception as exc:
        raise GenericEventError("EVENT_ENVELOPE_INVALID", "event envelope is invalid", 400) from exc

    if event.environment != expected_environment:
        raise GenericEventError("EVENT_ENVIRONMENT_DENIED", "event environment is not permitted", 403)
    current = now or datetime.now(UTC)
    if event.expires_at <= current:
        raise GenericEventError("EVENT_EXPIRED", "event has expired", 410)
    if (event.expires_at - event.occurred_at).total_seconds() > max_lifetime_seconds:
        raise GenericEventError("EVENT_LIFETIME_INVALID", "event lifetime is too long", 422)
    if event.occurred_at > current + timedelta(seconds=30):
        raise GenericEventError("EVENT_TIMESTAMP_INVALID", "event timestamp is invalid", 422)

    schema = registry.resolve(
        event_type=event.event_type,
        schema_version=event.schema_version,
        producer_service=event.producer.service_key,
    )
    payload_hash = _digest(event.payload_hash)
    if canonical_hash(event.payload) != payload_hash:
        raise GenericEventError("EVENT_PAYLOAD_HASH_MISMATCH", "payload hash does not match", 409)
    missing = schema.required_payload_fields.difference(event.payload)
    if missing:
        raise GenericEventError("EVENT_PAYLOAD_INVALID", "required payload field is missing", 422)
    return event
