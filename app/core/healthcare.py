"""Fail-closed healthcare transportation policy contracts."""
from dataclasses import dataclass

TRIP_STATES = frozenset({"DRAFT", "SUBMITTED", "VALIDATING", "ELIGIBILITY_PENDING", "AUTHORIZATION_PENDING", "SCHEDULING", "READY_FOR_DISPATCH", "DISPATCHED", "DRIVER_ASSIGNED", "EN_ROUTE_TO_PICKUP", "ARRIVED_PICKUP", "PATIENT_ONBOARD", "IN_TRANSIT", "ARRIVED_DESTINATION", "COMPLETED", "CANCELLED", "NO_SHOW", "FAILED", "ON_HOLD", "REVIEW_REQUIRED"})
SERVICE_LEVELS = frozenset({"AMBULATORY", "WHEELCHAIR", "STRETCHER", "BARIATRIC", "ESCORT_REQUIRED", "ASSISTANCE_REQUIRED", "FACILITY_DEFINED", "OTHER_APPROVED"})


class HealthcarePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class DispatchAuthorization:
    tenant_id: str
    trip_id: str
    authorized_role: bool
    eligibility_status: str
    authorization_status: str
    provider_available: bool
    emergency_dispatch: bool = False


def authorize_dispatch(request: DispatchAuthorization) -> bool:
    if not request.tenant_id or not request.trip_id or not request.authorized_role:
        return False
    if request.eligibility_status not in {"ELIGIBLE", "NOT_REQUIRED"} or request.authorization_status not in {"APPROVED", "NOT_REQUIRED"}:
        return False
    return request.provider_available and not request.emergency_dispatch


def validate_service_level(level: str) -> str:
    if level not in SERVICE_LEVELS:
        raise HealthcarePolicyError("service level requires approved value")
    return level
