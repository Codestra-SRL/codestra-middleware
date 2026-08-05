from datetime import datetime, time, timezone

from app.core.telephony_campaigns import CallingWindow, LeadEligibility, attempt_allowed, calling_allowed, lead_is_eligible
from app.core.telephony_commercial import TelephonyUsage, entitlement_allows, valid_usage
from app.core.telephony_releases import ReleaseGateSet, production_release_ready
from app.core.telephony_security import TelephonySecurityPolicy, authorize_destination, public_management_access_allowed, recording_access_allowed


def test_campaign_schedule_consent_and_attempt_guards():
    now = datetime(2026, 8, 5, 10, 0, tzinfo=timezone.utc)
    window = CallingWindow("UTC", time(9), time(17), frozenset({0, 1, 2, 3, 4}))
    assert calling_allowed(now=now, window=window)
    lead = LeadEligibility("t", "w", "c", "+18005550100", "GRANTED", False)
    assert lead_is_eligible(lead, now=now)
    assert not attempt_allowed(attempts_today=3, total_attempts=3, max_per_day=3, max_total=5, last_attempt_at=None, now=now, retry_interval_seconds=60)


def test_telephony_security_and_usage_are_scoped():
    policy = TelephonySecurityPolicy(frozenset({"+18005550100"}), 600, 2)
    assert authorize_destination("+18005550100", policy)
    assert not authorize_destination("+441234567890", policy)
    assert public_management_access_allowed(ami_public=False, ari_public=False)
    assert recording_access_allowed(tenant_id="t", requested_tenant_id="t", authorized=True)
    assert valid_usage(TelephonyUsage("t", "w", "OUTBOUND_MINUTES", 1, "minute", "usage-1234"))
    assert entitlement_allows(current=1, limit=10) == "ALLOWED_WITH_LIMIT"


def test_release_gates_require_backup_rollback_security_routing_and_monitoring():
    gates = ReleaseGateSet(True, True, True, True, True)
    assert production_release_ready(gates)
    assert not production_release_ready(ReleaseGateSet(True, False, True, True, True))
