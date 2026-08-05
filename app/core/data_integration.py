"""Fail-closed enterprise data and connector contracts."""
from dataclasses import dataclass

CONNECTOR_STATES = frozenset({"DRAFT", "SANDBOX", "ACTIVE", "PAUSED", "DEGRADED", "REVOKED"})
DATA_CLASSIFICATIONS = frozenset({"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "REGULATED", "SECRET"})


@dataclass(frozen=True)
class DataRecord:
    tenant_id: str
    workspace_id: str
    entity_type: str
    entity_key: str
    classification: str
    source_system: str


@dataclass(frozen=True)
class ConnectorRequest:
    tenant_id: str
    workspace_id: str
    connector_code: str
    version: str
    idempotency_key: str
    sandbox: bool
    permission_granted: bool
    retryable: bool = False


def validate_data_record(record: DataRecord) -> bool:
    return bool(record.tenant_id and record.workspace_id and record.entity_type and record.entity_key and record.source_system and record.classification in DATA_CLASSIFICATIONS)


def authorize_connector(request: ConnectorRequest) -> tuple[bool, str]:
    if not all((request.tenant_id, request.workspace_id, request.connector_code, request.version, request.idempotency_key)):
        return False, "MISSING_CONTEXT"
    if not request.permission_granted:
        return False, "PERMISSION_DENIED"
    if not request.sandbox:
        return False, "PRODUCTION_CONNECTOR_DISABLED"
    return True, "VALID"


def retry_allowed(*, retryable: bool, attempt: int, max_attempts: int) -> bool:
    return bool(retryable and 0 <= attempt < max_attempts)


def idempotency_is_new(*, existing_key: str | None, request_key: str) -> bool:
    return bool(request_key and existing_key != request_key)
