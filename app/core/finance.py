"""Fail-closed loan and financial-services workflow policy contracts."""
from dataclasses import dataclass

APPLICATION_STATES = frozenset({
    "DRAFT", "STARTED", "IDENTITY_PENDING", "CONSENT_PENDING", "DISCLOSURE_PENDING",
    "DOCUMENTS_PENDING", "DOCUMENT_REVIEW", "VERIFICATION_PENDING", "READY_FOR_REVIEW",
    "IN_REVIEW", "MORE_INFORMATION_REQUIRED", "MATCHING", "MATCHED", "OFFERS_AVAILABLE",
    "OFFER_SELECTED", "SUBMISSION_PENDING", "SUBMITTED", "LENDER_REVIEW",
    "APPROVED_BY_LENDER", "CONDITIONALLY_APPROVED", "DENIED_BY_LENDER", "WITHDRAWN",
    "EXPIRED", "SERVICING_HANDOFF", "CLOSED", "CANCELLED", "ERROR", "RECONCILIATION_REQUIRED",
})
VERIFICATION_STATES = frozenset({"NOT_REQUESTED", "PENDING", "VERIFIED", "FAILED", "UNKNOWN", "MANUAL_REVIEW_REQUIRED"})
MATCH_OUTCOMES = frozenset({"POTENTIAL_MATCH", "REVIEW_REQUIRED", "NOT_ELIGIBLE_BY_RULE", "INSUFFICIENT_INFORMATION", "PRODUCT_UNAVAILABLE"})


class FinancePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class SubmissionAuthorization:
    tenant_id: str
    application_id: str
    authorized_role: bool
    consent_accepted: bool
    disclosures_complete: bool
    human_reviewed: bool
    lender_authorized: bool = False


def authorize_submission(request: SubmissionAuthorization) -> bool:
    """Require explicit consent, disclosures, and human/authoritative review."""
    return bool(
        request.tenant_id
        and request.application_id
        and request.authorized_role
        and request.consent_accepted
        and request.disclosures_complete
        and (request.human_reviewed or request.lender_authorized)
    )


def validate_application_state(state: str) -> str:
    if state not in APPLICATION_STATES:
        raise FinancePolicyError("application state requires approved value")
    return state


def validate_match_outcome(outcome: str) -> str:
    if outcome not in MATCH_OUTCOMES:
        raise FinancePolicyError("match outcome requires approved value")
    return outcome
