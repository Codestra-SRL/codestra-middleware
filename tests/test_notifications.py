from datetime import datetime, time, timedelta, timezone

import pytest

from app.core.notifications import (
    Channel,
    CommandState,
    Decision,
    InvalidNotificationTransition,
    PolicyInput,
    can_dispatch,
    evaluate_policy,
    payload_digest,
    validate_transition,
)


def policy(**overrides):
    now = datetime(2026, 7, 28, 15, tzinfo=timezone.utc)
    values = {
        "channel": Channel.EMAIL,
        "organization_id": "ORG-1",
        "business_unit_id": "BU-1",
        "campaign_id": "CMP-1",
        "sender_profile_id": "SENDER-1",
        "destination_classification": "APPROVED_EMPLOYEE_TEST",
        "purpose": "INTERNAL_CANARY",
        "policy_hash": "a" * 64,
        "current_policy_hash": "a" * 64,
        "consent_granted": True,
        "suppression_active": False,
        "feature_enabled": True,
        "scope_allowed": True,
        "sender_approved": True,
        "destination_allowed": True,
        "approval_present": True,
        "rate_remaining": 1,
        "estimated_cost_minor": 1,
        "cost_remaining_minor": 10,
        "requested_at": now,
        "expires_at": now + timedelta(minutes=5),
    }
    values.update(overrides)
    return PolicyInput(**values)


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"feature_enabled": False}, Decision.FEATURE_DISABLED),
        ({"scope_allowed": False}, Decision.SCOPE_MISMATCH),
        ({"current_policy_hash": "b" * 64}, Decision.POLICY_STALE),
        ({"approval_present": False}, Decision.APPROVAL_REQUIRED),
        ({"consent_granted": False}, Decision.CONSENT_MISSING),
        ({"suppression_active": True}, Decision.SUPPRESSED),
        ({"sender_approved": False}, Decision.DESTINATION_PROHIBITED),
        ({"destination_allowed": False}, Decision.DESTINATION_PROHIBITED),
        ({"rate_remaining": 0}, Decision.RATE_LIMITED),
        ({"estimated_cost_minor": 11}, Decision.COST_LIMITED),
    ],
)
def test_policy_fails_closed(override, expected):
    assert evaluate_policy(policy(**override)) is expected


def test_policy_allows_only_complete_scope():
    assert evaluate_policy(policy()) is Decision.ALLOW


def test_quiet_hours_cross_midnight():
    assert (
        evaluate_policy(
            policy(
                requested_at=datetime(2026, 7, 28, 23, tzinfo=timezone.utc),
                expires_at=datetime(2026, 7, 29, 0, tzinfo=timezone.utc),
                quiet_hours_start=time(22),
                quiet_hours_end=time(8),
            )
        )
        is Decision.QUIET_HOURS
    )


def test_dispatch_requires_both_switches():
    assert not can_dispatch(
        channel=Channel.EMAIL, allow_live=False, dispatcher_enabled=True
    )
    assert not can_dispatch(
        channel=Channel.EMAIL, allow_live=True, dispatcher_enabled=False
    )
    assert can_dispatch(channel=Channel.EMAIL, allow_live=True, dispatcher_enabled=True)


def test_no_requested_to_completed_jump():
    with pytest.raises(InvalidNotificationTransition):
        validate_transition(CommandState.REQUESTED, CommandState.DELIVERED)


def test_terminal_state_cannot_transition():
    with pytest.raises(InvalidNotificationTransition):
        validate_transition(CommandState.SUPPRESSED, CommandState.QUEUED)


def test_reviewed_path_reaches_reservation():
    validate_transition(CommandState.REQUESTED, CommandState.VALIDATING)
    validate_transition(CommandState.VALIDATING, CommandState.VALIDATED)
    validate_transition(CommandState.VALIDATED, CommandState.AUTHORIZING)
    validate_transition(CommandState.AUTHORIZING, CommandState.AUTHORIZED)
    validate_transition(CommandState.AUTHORIZED, CommandState.RESERVED)


def test_payload_hash_is_exact_bytes():
    assert (
        payload_digest(b"{}")
        == "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"
    )
