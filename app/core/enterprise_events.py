"""Validation and hashing for immutable enterprise event envelopes."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


class EnterpriseEventError(ValueError):
    pass


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    aggregate_type: str
    aggregate_id: str
    aggregate_sequence: int
    event_type: str
    schema_version: str
    payload: dict[str, Any]
    occurred_at: datetime
    correlation_id: str
    causation_id: str | None = None

    def validate(self) -> None:
        if not EVENT_NAME.fullmatch(self.event_type):
            raise EnterpriseEventError("event type invalid")
        if self.aggregate_sequence < 1:
            raise EnterpriseEventError("aggregate sequence invalid")
        if not all((self.event_id, self.aggregate_type, self.aggregate_id, self.schema_version, self.correlation_id)):
            raise EnterpriseEventError("event identity incomplete")
        encoded = json.dumps(self.payload, sort_keys=True, separators=(",", ":")).encode()
        if len(encoded) > 262_144:
            raise EnterpriseEventError("event payload too large")


def idempotency_hash(tenant_id: str, workspace_id: str, key: str) -> str:
    if not key or len(key) > 255:
        raise EnterpriseEventError("idempotency key invalid")
    canonical = "\n".join((tenant_id, workspace_id, key)).encode()
    return hashlib.sha256(canonical).hexdigest()
