import pytest

from app.core.support import (
    ReplyAuthorization,
    RoutingDecision,
    SupportPolicyError,
    authorize_reply,
    authorize_routing,
    validate_priority,
    validate_ticket_state,
)


def test_ticket_state_and_priority_are_explicit():
    assert validate_ticket_state("IN_PROGRESS") == "IN_PROGRESS"
    assert validate_priority("URGENT") == "URGENT"


def test_invalid_support_values_fail_closed():
    with pytest.raises(SupportPolicyError):
        validate_ticket_state("AUTO_CLOSED")
    with pytest.raises(SupportPolicyError):
        validate_priority("VIP")


def test_routing_requires_tenant_queue_and_known_outcome():
    assert authorize_routing(RoutingDecision("tenant-a", "EMAIL", "queue-a", True, "QUEUED")) is True
    assert authorize_routing(RoutingDecision("tenant-a", "EMAIL", "", True, "QUEUED")) is False


def test_customer_reply_requires_human_confirmation():
    assert authorize_reply(ReplyAuthorization("tenant-a", "ticket-a", "agent-a", True)) is True
    assert authorize_reply(ReplyAuthorization("tenant-a", "ticket-a", "agent-a", False)) is False

