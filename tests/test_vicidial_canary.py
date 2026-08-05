from datetime import UTC, datetime, timedelta

import pytest

from app.adapters.vicidial.canary import CanaryRuntimeSnapshot, VicidialCanaryAdapter
from app.core.vicidial_canary import CanaryAuthorization, CanaryGateError, enforce_limits, normalize_phone, phone_hash


def auth() -> CanaryAuthorization:
    now = datetime.now(UTC)
    return CanaryAuthorization("STAGING_CAMPAIGN", "STAGING_LEADS", now - timedelta(minutes=1), now + timedelta(minutes=1), "AUTH-TEST-001", "reviewer")


def test_phone_is_hashed_and_normalized():
    assert normalize_phone("+1 (305) 555-0100") == "+13055550100"
    assert len(phone_hash("+13055550100")) == 64


def test_limits_are_exactly_one():
    with pytest.raises(CanaryGateError):
        enforce_limits(call_count=1, lead_count=0)
    with pytest.raises(CanaryGateError):
        enforce_limits(call_count=0, lead_count=1)


def test_adapter_blocks_without_live_authorization():
    adapter = VicidialCanaryAdapter()
    snapshot = CanaryRuntimeSnapshot("STAGING_CAMPAIGN", "STAGING_LEADS", False, 0, False, True, 1)
    with pytest.raises(CanaryGateError, match="authorization"):
        adapter.authorize_one_call(snapshot=snapshot, authorization=auth(), call_count=0, lead_count=0, live_authorized=False)


def test_adapter_rejects_hopper_or_missing_capacity():
    adapter = VicidialCanaryAdapter()
    with pytest.raises(CanaryGateError, match="hopper"):
        adapter.authorize_one_call(snapshot=CanaryRuntimeSnapshot("STAGING_CAMPAIGN", "STAGING_LEADS", False, 1, False, True, 1), authorization=auth(), call_count=0, lead_count=0, live_authorized=True)
    with pytest.raises(CanaryGateError, match="capacity"):
        adapter.authorize_one_call(snapshot=CanaryRuntimeSnapshot("STAGING_CAMPAIGN", "STAGING_LEADS", False, 0, False, True, 0), authorization=auth(), call_count=0, lead_count=0, live_authorized=True)
