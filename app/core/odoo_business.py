"""Durable, tenant-scoped Odoo business command primitives.

Odoo remains the system of record.  Middleware stores commands, delivery state,
references, reconciliation state, and privacy-safe audit metadata only.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Final, Literal


class OdooBusinessError(ValueError):
    """Raised when a business command violates the stable contract."""


RESOURCE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "customer", "company", "contact", "lead", "crm_opportunity",
        "activity", "appointment", "project", "task", "support_ticket",
        "call", "callback", "recording", "transcript", "voice_ai_session",
        "ai_employee", "marketplace_listing", "commercial_record",
        "subscription", "usage_record", "sla", "customer_health",
        "document", "knowledge_article", "audit_record",
    }
)
OPERATIONS: Final[frozenset[str]] = frozenset(
    {"create", "update", "archive", "link", "transition"}
)
APPROVAL_REQUIRED: Final[frozenset[str]] = frozenset(
    {"archive", "transition"}
)
RESOURCE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def payload_hash(value: dict[str, object]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode()).hexdigest()


def scoped_idempotency_hash(
    tenant_id: str, workspace_id: str, resource_type: str, key: str
) -> str:
    if not (8 <= len(key) <= 200):
        raise OdooBusinessError("idempotency key length invalid")
    material = "\n".join((tenant_id, workspace_id, resource_type, key))
    return hashlib.sha256(material.encode()).hexdigest()


def validate_payload(payload: dict[str, object]) -> None:
    encoded = canonical_json(payload).encode()
    if not payload:
        raise OdooBusinessError("payload must not be empty")
    if len(encoded) > 131_072:
        raise OdooBusinessError("payload exceeds 128 KiB")
    forbidden = {
        "model", "model_name", "record_id", "odoo_id", "database", "db",
        "password", "token", "api_key", "secret", "access_token",
    }
    keys = {str(key).lower() for key in payload}
    if keys.intersection(forbidden):
        raise OdooBusinessError("privileged or secret-bearing field rejected")


@dataclass(frozen=True)
class BusinessCommand:
    resource_type: str
    operation: Literal["create", "update", "archive", "link", "transition"]
    resource_key: str
    payload: dict[str, object]
    expected_version: int | None = None

    def validate(self) -> None:
        if self.resource_type not in RESOURCE_TYPES:
            raise OdooBusinessError("resource type unsupported")
        if self.operation not in OPERATIONS:
            raise OdooBusinessError("operation unsupported")
        if not RESOURCE_KEY.fullmatch(self.resource_key):
            raise OdooBusinessError("resource key invalid")
        if self.expected_version is not None and self.expected_version < 1:
            raise OdooBusinessError("expected version invalid")
        validate_payload(self.payload)

    @property
    def approval_required(self) -> bool:
        return self.operation in APPROVAL_REQUIRED


SERVICE_RESOURCE_GROUPS: Final[dict[str, frozenset[str]]] = {
    "customer": frozenset({"customer", "company", "contact"}),
    "lead": frozenset({"lead", "crm_opportunity"}),
    "activity": frozenset({"activity"}),
    "project": frozenset({"project", "task"}),
    "appointment": frozenset({"appointment"}),
    "support": frozenset({"support_ticket", "sla", "customer_health"}),
    "voice": frozenset({"call", "callback", "recording", "transcript", "voice_ai_session"}),
    "ai": frozenset({"ai_employee", "document", "knowledge_article"}),
    "marketplace": frozenset({"marketplace_listing"}),
    "commercial": frozenset({"commercial_record", "subscription"}),
    "usage": frozenset({"usage_record"}),
    "audit": frozenset({"audit_record"}),
}
