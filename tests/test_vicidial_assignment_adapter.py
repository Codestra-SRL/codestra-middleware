import pytest

from app.adapters.vicidial.assignment import VicidialAssignmentAdapter, VicidialAssignmentError


class MockPort:
    def __init__(self):
        self.calls = []

    async def request(self, operation, payload, *, idempotency_key):
        self.calls.append((operation, payload, idempotency_key))
        return {"found": False, "accepted": True}


@pytest.mark.asyncio
async def test_adapter_allows_only_disabled_staging_target():
    port = MockPort()
    adapter = VicidialAssignmentAdapter(port)
    result = await adapter.assign_lead({"campaign_id": "STAGING_CAMPAIGN", "list_id": "STAGING_LEADS", "external_key": "codestra:t:vicidial-lead:l", "dialing_enabled": False}, idempotency_key="item-1")
    assert result["accepted"] and port.calls[0][0] == "create_lead_in_approved_list"


@pytest.mark.asyncio
async def test_adapter_rejects_live_target_and_dialing():
    adapter = VicidialAssignmentAdapter(MockPort())
    with pytest.raises(VicidialAssignmentError):
        await adapter.assign_lead({"campaign_id": "LIVE", "list_id": "STAGING_LEADS", "external_key": "x", "dialing_enabled": False}, idempotency_key="x")
    with pytest.raises(VicidialAssignmentError):
        await adapter.assign_lead({"campaign_id": "STAGING_CAMPAIGN", "list_id": "STAGING_LEADS", "external_key": "x", "dialing_enabled": True}, idempotency_key="x")

