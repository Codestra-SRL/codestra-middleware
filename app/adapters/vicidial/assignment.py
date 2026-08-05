"""Allowlisted VICIdial staging assignment adapter.

The adapter is deliberately separate from transfer control and refuses any
campaign, list, dial, SQL, agent, carrier, or delete operation outside the
explicit staging lead contract.
"""

from __future__ import annotations

from typing import Any, Protocol


ALLOWED_OPERATIONS = frozenset(
    {
        "health_check",
        "list_campaigns_read_only",
        "list_lists_read_only",
        "read_lead",
        "find_lead_by_external_key",
        "find_lead_by_phone",
        "create_lead_in_approved_list",
        "read_assignment_status",
    }
)


class VicidialAssignmentError(RuntimeError):
    pass


class VicidialAssignmentPort(Protocol):
    async def request(self, operation: str, payload: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]: ...


class VicidialAssignmentAdapter:
    def __init__(self, client: VicidialAssignmentPort, *, staging_campaign: str = "STAGING_CAMPAIGN", staging_list: str = "STAGING_LEADS") -> None:
        self.client = client
        self.staging_campaign = staging_campaign
        self.staging_list = staging_list

    async def assign_lead(self, payload: dict[str, Any], *, idempotency_key: str) -> dict[str, Any]:
        if payload.get("campaign_id") != self.staging_campaign or payload.get("list_id") != self.staging_list:
            raise VicidialAssignmentError("only the disabled staging target is allowed")
        if payload.get("dialing_enabled") is not False:
            raise VicidialAssignmentError("dialing must remain disabled")
        if not payload.get("external_key"):
            raise VicidialAssignmentError("external key is required")
        return await self.client.request("create_lead_in_approved_list", payload, idempotency_key=idempotency_key)

    async def find_existing(self, external_key: str, *, phone: str = "") -> dict[str, Any]:
        if not external_key:
            raise VicidialAssignmentError("external key is required")
        result = await self.client.request("find_lead_by_external_key", {"external_key": external_key}, idempotency_key=f"lookup:{external_key}")
        if result.get("found") or not phone:
            return result
        return await self.client.request("find_lead_by_phone", {"phone": phone, "list_id": self.staging_list}, idempotency_key=f"lookup-phone:{phone}")

