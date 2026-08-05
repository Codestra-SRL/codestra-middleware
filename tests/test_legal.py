import pytest

from app.core.legal import (
    EthicalWallDecision,
    LegalPolicyError,
    MatterOpeningAuthorization,
    allow_matter_access,
    authorize_matter_opening,
    validate_conflict_outcome,
    validate_intake_state,
)


def test_intake_states_are_explicit():
    assert validate_intake_state("CONFLICT_REVIEW") == "CONFLICT_REVIEW"


def test_invalid_intake_state_fails_closed():
    with pytest.raises(LegalPolicyError):
        validate_intake_state("AUTO_ACCEPTED")


def test_conflict_outcomes_require_known_values():
    assert validate_conflict_outcome("POTENTIAL_CONFLICT") == "POTENTIAL_CONFLICT"
    with pytest.raises(LegalPolicyError):
        validate_conflict_outcome("AI_CLEARED")


def test_matter_opening_requires_conflict_engagement_owner_and_controls():
    request = MatterOpeningAuthorization("tenant-a", "matter-a", True, True, True, True, True)
    assert authorize_matter_opening(request) is True
    assert authorize_matter_opening(
        MatterOpeningAuthorization("tenant-a", "matter-a", True, False, True, True, True)
    ) is False


def test_ethical_wall_blocks_access_even_for_authenticated_user():
    assert allow_matter_access(EthicalWallDecision("tenant-a", "matter-a", "user-a", True)) is False
    assert allow_matter_access(EthicalWallDecision("tenant-a", "matter-a", "user-a", True, True, "incident review")) is False


def test_ethical_wall_override_requires_reason_and_privileged_path():
    assert allow_matter_access(EthicalWallDecision("tenant-a", "matter-a", "user-a", False)) is False
    assert allow_matter_access(EthicalWallDecision("tenant-a", "matter-a", "user-a", False, True, "approved review")) is True
