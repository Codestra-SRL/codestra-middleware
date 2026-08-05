import pytest

from app.core.revops import (
    CommissionApproval,
    ForecastObservation,
    RevOpsPolicyError,
    authorize_commission,
    normalize_advisory_score,
    validate_campaign_state,
    validate_opportunity_state,
)


def test_pipeline_and_campaign_states_are_explicit():
    assert validate_opportunity_state("NEGOTIATION") == "NEGOTIATION"
    assert validate_campaign_state("IN_REVIEW") == "IN_REVIEW"


def test_invalid_revops_states_fail_closed():
    with pytest.raises(RevOpsPolicyError):
        validate_opportunity_state("AUTO_WON")
    with pytest.raises(RevOpsPolicyError):
        validate_campaign_state("AUTO_PUBLISHED")


def test_forecasts_remain_advisory_and_bounded():
    assert normalize_advisory_score(ForecastObservation("tenant-a", "opp-a", 0.7)) == 0.7
    with pytest.raises(RevOpsPolicyError):
        normalize_advisory_score(ForecastObservation("tenant-a", "opp-a", 1.2))


def test_commissions_require_human_and_pricing_approval():
    assert authorize_commission(CommissionApproval("tenant-a", "opp-a", 100, True, True)) is True
    assert authorize_commission(CommissionApproval("tenant-a", "opp-a", 100, False, True)) is False

