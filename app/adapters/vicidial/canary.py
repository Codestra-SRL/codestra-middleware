"""Allowlisted, fail-closed campaign canary adapter.

Network execution is intentionally not implemented here. Runtime adapters must
be supplied only after server access, written authorization and a test number
are verified; these methods provide the safety contract for that integration.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.vicidial_canary import CanaryAuthorization, CanaryGateError, enforce_campaign_safety, enforce_limits


@dataclass(frozen=True)
class CanaryRuntimeSnapshot:
    campaign_id: str
    list_id: str
    active: bool
    hopper_count: int
    dialing_enabled: bool
    carrier_available: bool
    agent_capacity: int


class VicidialCanaryAdapter:
    """Governance-only adapter; never creates calls without explicit gates."""

    def validate_snapshot(self, snapshot: CanaryRuntimeSnapshot, authorization: CanaryAuthorization) -> None:
        enforce_campaign_safety(
            campaign_id=snapshot.campaign_id,
            list_id=snapshot.list_id,
            active=snapshot.active,
            hopper_count=snapshot.hopper_count,
            dialing_enabled=snapshot.dialing_enabled,
            authorization=authorization,
        )
        if not snapshot.carrier_available:
            raise CanaryGateError("carrier availability check failed")
        if snapshot.agent_capacity < 1:
            raise CanaryGateError("approved agent capacity is unavailable")

    def authorize_one_call(self, *, snapshot: CanaryRuntimeSnapshot, authorization: CanaryAuthorization, call_count: int, lead_count: int, live_authorized: bool) -> None:
        if not live_authorized:
            raise CanaryGateError("live canary authorization is disabled")
        self.validate_snapshot(snapshot, authorization)
        enforce_limits(call_count=call_count, lead_count=lead_count, max_calls=1, max_leads=1)

    def place_one_call(self, **_: object) -> None:
        raise CanaryGateError("live call execution requires an approved runtime adapter and explicit authorization")
