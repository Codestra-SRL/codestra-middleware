"""Non-destructive telephony security contracts."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TelephonySecurityPolicy:
    allowed_destinations: frozenset[str]
    max_duration_seconds: int
    max_concurrent_channels: int
    ami_public: bool = False
    ari_public: bool = False


def authorize_destination(number: str, policy: TelephonySecurityPolicy) -> bool:
    return bool(number and number in policy.allowed_destinations)


def public_management_access_allowed(*, ami_public: bool, ari_public: bool) -> bool:
    return not ami_public and not ari_public


def recording_access_allowed(*, tenant_id: str, requested_tenant_id: str, authorized: bool) -> bool:
    return bool(tenant_id and tenant_id == requested_tenant_id and authorized)
