"""Versioned generic integration-event contracts.

This module deliberately contains contract shapes only.  Active event bindings
are deployment data and are resolved by the schema registry service.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GenericProducer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_key: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=64)


class GenericPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=64)
    hash: str = Field(pattern=r"^(?:sha256:)?[0-9a-f]{64}$")


class GenericEvent(BaseModel):
    """Canonical event envelope accepted by the generic middleware gateway."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1, max_length=16)
    event_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(min_length=1, max_length=128)
    event_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=255)
    correlation_id: str = Field(min_length=1, max_length=128)
    causation_id: str = Field(min_length=1, max_length=128)
    environment: str = Field(min_length=1, max_length=32)
    organization_public_id: str = Field(min_length=1, max_length=128)
    business_unit_public_id: str = Field(min_length=1, max_length=128)
    campaign_public_id: str | None = Field(default=None, max_length=128)
    producer: GenericProducer
    policy: GenericPolicy
    occurred_at: datetime
    expires_at: datetime
    payload_hash: str = Field(pattern=r"^(?:sha256:)?[0-9a-f]{64}$")
    payload: dict[str, Any]

