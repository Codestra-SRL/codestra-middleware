import pytest

from app.core.healthcare import (
    DispatchAuthorization,
    HealthcarePolicyError,
    authorize_dispatch,
    validate_service_level,
)


def test_approved_service_levels_are_explicit():
    assert validate_service_level("WHEELCHAIR") == "WHEELCHAIR"


def test_unapproved_service_level_fails_closed():
    with pytest.raises(HealthcarePolicyError):
        validate_service_level("CLINICAL_TRIAGE")


def test_dispatch_requires_authoritative_clearance():
    request = DispatchAuthorization(
        tenant_id="tenant-a",
        trip_id="trip-a",
        authorized_role=True,
        eligibility_status="ELIGIBLE",
        authorization_status="APPROVED",
        provider_available=True,
    )
    assert authorize_dispatch(request) is True

    assert authorize_dispatch(
        DispatchAuthorization(
            tenant_id="tenant-a",
            trip_id="trip-a",
            authorized_role=True,
            eligibility_status="UNKNOWN",
            authorization_status="APPROVED",
            provider_available=True,
        )
    ) is False


def test_emergency_dispatch_is_never_authorized_by_healthcare_control_plane():
    assert authorize_dispatch(
        DispatchAuthorization(
            tenant_id="tenant-a",
            trip_id="trip-a",
            authorized_role=True,
            eligibility_status="NOT_REQUIRED",
            authorization_status="NOT_REQUIRED",
            provider_available=True,
            emergency_dispatch=True,
        )
    ) is False
