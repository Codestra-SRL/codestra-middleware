import pytest

from app.core.vicidial_assignment import AssignmentPolicy, AssignmentPolicyError, eligibility_errors, external_key, transition


def eligible():
    return {"approved_for_import": True, "odoo_lead_id": 7, "external_key": "codestra:t:vicidial-lead:l", "normalized_phone": "+13055550100", "phone_confidence": 0.9, "duplicate_status": "UNREVIEWED", "suppressed": False}


def test_eligibility_accepts_only_staging_targets():
    assert eligibility_errors(eligible(), AssignmentPolicy(), target_campaign="STAGING_CAMPAIGN", target_list="STAGING_LEADS") == []
    assert "campaign_not_allowed" in eligibility_errors(eligible(), AssignmentPolicy(), target_campaign="LIVE", target_list="STAGING_LEADS")


def test_suppression_duplicate_and_live_dialing_are_blocked():
    assert "suppression_blocked" in eligibility_errors({**eligible(), "suppressed": True}, AssignmentPolicy(), target_campaign="STAGING_CAMPAIGN", target_list="STAGING_LEADS")
    assert "duplicate_blocked" in eligibility_errors({**eligible(), "duplicate_status": "CONFIRMED_DUPLICATE"}, AssignmentPolicy(), target_campaign="STAGING_CAMPAIGN", target_list="STAGING_LEADS")
    assert AssignmentPolicy().allow_live_dialing is False


def test_assignment_state_and_external_key_are_fail_closed():
    assert transition("ELIGIBLE", "APPROVED_FOR_ASSIGNMENT") == "APPROVED_FOR_ASSIGNMENT"
    with pytest.raises(AssignmentPolicyError):
        transition("ASSIGNED", "ASSIGNING")
    assert external_key("tenant", "lead") == "codestra:tenant:vicidial-lead:lead"

