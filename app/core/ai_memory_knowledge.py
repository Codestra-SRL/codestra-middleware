"""Fail-closed contracts for governed memory and knowledge retrieval."""
from dataclasses import dataclass

MEMORY_STATES = frozenset({"CAPTURED", "PENDING_CLASSIFICATION", "PENDING_REVIEW", "APPROVED", "INDEXING", "ACTIVE", "CORRECTION_PENDING", "SUPERSEDED", "EXPIRED", "REVOKED", "LEGAL_HOLD", "DELETION_PENDING", "DELETED", "INDEXING_FAILED", "RECONCILIATION_REQUIRED"})
CLASSIFICATIONS = frozenset({"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PRIVILEGED", "REGULATED", "SECRET"})


@dataclass(frozen=True)
class RetrievalContext:
    tenant_id: str
    workspace_id: str
    employee_id: str
    permissions: frozenset[str]
    requested_scope: str
    source_states: frozenset[str] = frozenset({"ACTIVE"})
    max_results: int = 10


@dataclass(frozen=True)
class RetrievalCandidate:
    tenant_id: str
    workspace_id: str
    classification: str
    state: str
    revoked: bool = False
    expired: bool = False
    legal_hold: bool = False


def authorize_retrieval(context: RetrievalContext) -> bool:
    """Require complete scope and an explicit active-source policy."""
    return bool(
        context.tenant_id
        and context.workspace_id
        and context.employee_id
        and context.requested_scope
        and context.source_states == frozenset({"ACTIVE"})
        and 0 < context.max_results <= 100
    )


def filter_candidate(context: RetrievalContext, candidate: RetrievalCandidate) -> bool:
    """Apply mandatory metadata filters before a vector result is usable."""
    if not authorize_retrieval(context):
        return False
    return bool(
        candidate.tenant_id == context.tenant_id
        and candidate.workspace_id == context.workspace_id
        and candidate.state == "ACTIVE"
        and not candidate.revoked
        and not candidate.expired
        and not candidate.legal_hold
        and candidate.classification in CLASSIFICATIONS
    )


def authorize_promotion(*, human_approved: bool, source_backed: bool, classification: str, contains_secret: bool) -> bool:
    """Long-term promotion requires review, evidence, valid classification, and no secrets."""
    return bool(human_approved and source_backed and classification in CLASSIFICATIONS - {"SECRET"} and not contains_secret)


def citation_is_resolvable(*, source_id: str, source_version: str, state: str, citation_label: str) -> bool:
    return bool(source_id and source_version and citation_label and state == "ACTIVE")
