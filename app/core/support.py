"""Fail-closed omnichannel support routing and response policy contracts."""
from dataclasses import dataclass

TICKET_STATES = frozenset({"NEW", "OPEN", "ASSIGNED", "IN_PROGRESS", "WAITING_FOR_CUSTOMER", "WAITING_FOR_INTERNAL_TEAM", "WAITING_FOR_EXTERNAL_PROVIDER", "ESCALATED", "RESOLVED", "CLOSED", "REOPENED", "SPAM", "DUPLICATE", "CANCELLED", "RECONCILIATION_REQUIRED"})
PRIORITIES = frozenset({"LOW", "NORMAL", "HIGH", "URGENT", "CRITICAL"})
ROUTING_OUTCOMES = frozenset({"ASSIGNED", "QUEUED", "ESCALATED", "MANUAL_REVIEW", "UNROUTABLE"})


class SupportPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class RoutingDecision:
    tenant_id: str
    channel: str
    queue_id: str
    authorized: bool
    outcome: str


@dataclass(frozen=True)
class ReplyAuthorization:
    tenant_id: str
    ticket_id: str
    agent_id: str
    human_confirmed: bool
    customer_visible: bool = True


def authorize_routing(decision: RoutingDecision) -> bool:
    return bool(decision.tenant_id and decision.channel and decision.queue_id and decision.authorized and decision.outcome in ROUTING_OUTCOMES)


def authorize_reply(reply: ReplyAuthorization) -> bool:
    return bool(reply.tenant_id and reply.ticket_id and reply.agent_id and reply.human_confirmed and reply.customer_visible)


def validate_ticket_state(state: str) -> str:
    if state not in TICKET_STATES:
        raise SupportPolicyError("ticket state requires approved value")
    return state


def validate_priority(priority: str) -> str:
    if priority not in PRIORITIES:
        raise SupportPolicyError("priority requires approved value")
    return priority
