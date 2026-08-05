import pytest

from app.core.finance import (
    FinancePolicyError,
    SubmissionAuthorization,
    authorize_submission,
    validate_application_state,
    validate_match_outcome,
)


def test_application_states_are_explicit():
    assert validate_application_state("DOCUMENTS_PENDING") == "DOCUMENTS_PENDING"


def test_unknown_application_state_fails_closed():
    with pytest.raises(FinancePolicyError):
        validate_application_state("AUTO_APPROVED")


def test_matching_outcomes_are_advisory():
    assert validate_match_outcome("POTENTIAL_MATCH") == "POTENTIAL_MATCH"
    with pytest.raises(FinancePolicyError):
        validate_match_outcome("GUARANTEED_APPROVAL")


def test_submission_requires_consent_disclosures_and_review():
    request = SubmissionAuthorization("tenant-a", "application-a", True, True, True, True)
    assert authorize_submission(request) is True
    assert authorize_submission(
        SubmissionAuthorization("tenant-a", "application-a", True, False, True, True)
    ) is False
    assert authorize_submission(
        SubmissionAuthorization("tenant-a", "application-a", True, True, True, False)
    ) is False


def test_lender_authority_can_satisfy_review_requirement():
    assert authorize_submission(
        SubmissionAuthorization("tenant-a", "application-a", True, True, True, False, True)
    ) is True
