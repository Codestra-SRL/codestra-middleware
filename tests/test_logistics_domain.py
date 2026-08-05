from fastapi import HTTPException
import pytest

from app.core.logistics import (
    LogisticsPrincipal,
    ORDER_TRANSITIONS,
    SHIPMENT_TRANSITIONS,
    request_hash,
    token_digest,
    validate_transition,
)
from app.core.logistics_routing import DeterministicMockRoutingProvider


def test_order_and_shipment_state_machines_fail_closed():
    validate_transition("DRAFT", "QUOTE_PENDING", ORDER_TRANSITIONS)
    validate_transition("CREATED", "AWAITING_DISPATCH", SHIPMENT_TRANSITIONS)
    with pytest.raises(HTTPException) as exc:
        validate_transition("CREATED", "DELIVERED", SHIPMENT_TRANSITIONS)
    assert exc.value.status_code == 409


def test_roles_do_not_allow_automatic_price_or_claim_decisions():
    manager = LogisticsPrincipal("user", "tenant", "workspace", frozenset({"LOGISTICS_MANAGER"}))
    manager.require("dispatch")
    for denied in ("automatic_dispatch", "automatic_pricing", "claim_decision"):
        with pytest.raises(HTTPException):
            manager.require(denied)


def test_tracking_tokens_are_stored_as_non_reversible_digests():
    token = "synthetic-tracking-token-that-is-not-a-reference"
    assert token not in token_digest(token)
    assert len(token_digest(token)) == 64


def test_request_hash_is_deterministic_and_order_independent():
    assert request_hash({"b": 2, "a": 1}) == request_hash({"a": 1, "b": 2})


def test_mock_routing_is_deterministic_and_explicitly_non_live():
    provider = DeterministicMockRoutingProvider()
    assert provider.calculate_distance((18.4, -69.9), (18.5, -70.0)) == 22.2
    assert provider.optimize_stop_order([(2, 1), (1, 2), (1, 1)]) == [2, 1, 0]
    assert provider.health_check()

