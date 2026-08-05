import pytest

from app.core.expansion import ExpansionGateError, ObservationSnapshot, evaluate_observation, transition


def test_expansion_transitions_are_fail_closed():
    assert transition("PLANNED", "AWAITING_APPROVAL") == "AWAITING_APPROVAL"
    with pytest.raises(ExpansionGateError):
        transition("PLANNED", "ACTIVE")


def test_dangerous_observation_requires_rollback():
    assert evaluate_observation(ObservationSnapshot(duplicate_count=1)) == "FAIL_ROLLBACK"
    assert evaluate_observation(ObservationSnapshot(live_calls=1)) == "FAIL_ROLLBACK"


def test_degraded_observation_pauses_stage():
    assert evaluate_observation(ObservationSnapshot(error_rate=0.02)) == "PAUSE"
    assert evaluate_observation(ObservationSnapshot(reconciliation_backlog=1)) == "PAUSE"


def test_clean_observation_passes():
    assert evaluate_observation(ObservationSnapshot()) == "PASS"
