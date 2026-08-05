import pytest

from app.core.lead_import import ApprovalPolicy, LeadImportPolicyError, approval_errors, external_key, transition


def valid_lead():
    return {
        "company_name": "Example Test LLC",
        "source_history": [{"source_url": "https://example.invalid"}],
        "normalized_phone": "+13055550100",
        "lead_score": 75,
        "ownership_status": "UNKNOWN",
        "ownership_confidence": 0,
        "duplicate_status": "UNREVIEWED",
    }


def test_review_approval_requires_policy_conditions():
    assert approval_errors(valid_lead(), ApprovalPolicy()) == []
    blocked = {**valid_lead(), "duplicate_status": "CONFIRMED_DUPLICATE"}
    assert "confirmed_duplicate" in approval_errors(blocked, ApprovalPolicy())


def test_unsupported_owner_claim_is_blocked():
    blocked = {**valid_lead(), "ownership_status": "CONFIRMED_OWNER", "ownership_confidence": 1}
    assert "unsupported_ownership_claim" in approval_errors(blocked, ApprovalPolicy())


def test_state_machine_and_external_key_are_fail_closed():
    assert transition("REVIEW_REQUIRED", "UNDER_REVIEW") == "UNDER_REVIEW"
    with pytest.raises(LeadImportPolicyError):
        transition("IMPORTED", "APPROVED_FOR_IMPORT")
    assert external_key("tenant-test", "lead-1") == "codestra:tenant-test:lead:lead-1"

