from app.core.commercial import EntitlementRequest, approve_service_credit, approve_suspension, decide_entitlement, usage_event_is_new


def test_entitlements_are_deterministic_and_scope_checked():
    assert decide_entitlement(EntitlementRequest("t1", "w1", "voice", 1, 3, True)) == "ALLOWED_WITH_LIMIT"
    assert decide_entitlement(EntitlementRequest("t1", "w1", "voice", 3, 3, True)) == "UPGRADE_REQUIRED"
    assert decide_entitlement(EntitlementRequest("t1", "w1", "voice", 0, 3, True, suspended=True)) == "SUSPENDED"
    assert decide_entitlement(EntitlementRequest("", "w1", "voice", 0, 3, True)) == "DENIED"


def test_usage_is_idempotent_and_sensitive_actions_need_humans():
    assert usage_event_is_new(existing_key=None, event_key="event-1")
    assert not usage_event_is_new(existing_key="event-1", event_key="event-1")
    assert approve_service_credit(human_approved=True, eligible=True, ai_requested=False)
    assert not approve_service_credit(human_approved=True, eligible=True, ai_requested=True)
    assert approve_suspension(human_approved=True, reason="security", scope="tenant")
    assert not approve_suspension(human_approved=False, reason="security", scope="tenant")
