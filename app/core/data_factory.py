"""Governed Data Factory contracts; storage and publication fail closed."""

from dataclasses import dataclass

DATA_SOURCE_STATES = frozenset({"DRAFT", "VALIDATING", "ACTIVE", "DEGRADED", "PAUSED", "SUSPENDED", "FAILED", "RETIRED"})
QUALITY_OUTCOMES = frozenset({"PASS", "PASS_WITH_WARNING", "FAIL", "QUARANTINE", "REVIEW_REQUIRED"})
RESOLUTION_OUTCOMES = frozenset({"EXACT_MATCH", "HIGH_CONFIDENCE_MATCH", "PROBABLE_MATCH", "MULTIPLE_MATCHES", "NO_MATCH", "CONFLICT", "HUMAN_REVIEW_REQUIRED"})


@dataclass(frozen=True)
class IngestionContext:
    source_code: str
    tenant_id: str
    workspace_id: str
    schema_version: str
    idempotency_key: str
    checksum: str


def validate_ingestion(context: IngestionContext) -> tuple[bool, str]:
    if not all((context.source_code, context.tenant_id, context.workspace_id, context.schema_version, context.idempotency_key, context.checksum)):
        return False, "MISSING_INGESTION_CONTEXT"
    return True, "VALID"


def quality_outcome(*, required_fields_present: bool, valid_values: bool, duplicate: bool = False) -> str:
    if duplicate:
        return "QUARANTINE"
    if not required_fields_present or not valid_values:
        return "FAIL"
    return "PASS"


def resolve_entity(*, exact_identifier: bool, similarity: float, conflicting_sources: bool = False) -> str:
    if conflicting_sources:
        return "CONFLICT"
    if exact_identifier:
        return "EXACT_MATCH"
    if similarity >= 0.95:
        return "HIGH_CONFIDENCE_MATCH"
    if similarity >= 0.80:
        return "PROBABLE_MATCH"
    return "NO_MATCH"


def lineage_is_traceable(*, source_reference: str, ingestion_run: str, product_reference: str) -> bool:
    return all((source_reference, ingestion_run, product_reference))
