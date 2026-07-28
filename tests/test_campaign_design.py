from dataclasses import replace
from uuid import uuid4

import pytest

from app.core.campaign_design import (
    CampaignDesignInput, CampaignDesignService, DesignConflict, StoredDesign,
    build_manifest,
)
from app.core.config import settings
from app.main import app


class MemoryStore:
    def __init__(self):
        self.events = {}
        self.designs = {}
        self.allocations = {}
        self.attempts = {}
        self.fail_create = False

    async def rollback(self):
        return None

    async def event(self, event_id):
        return self.events.get(event_id)

    async def design(self, integration_uuid):
        return self.designs.get(integration_uuid)

    async def create(self, request):
        if self.fail_create:
            raise RuntimeError("synthetic dependency failure")
        low = 91000 if request.business_unit == "TEST" else {
            "MOY": 11000, "COD": 21000,
        }.get(request.business_unit, 31000)
        used = self.allocations.setdefault(
            (request.environment, request.business_unit), set()
        )
        list_id = next(item for item in range(low, low + 1000) if item not in used)
        used.add(list_id)
        manifest = build_manifest(request, 1, list_id)
        stored = StoredDesign(1, manifest, request.payload_hash(), "preview")
        self.designs[request.integration_uuid] = stored
        return stored

    async def mark_event(self, request, status):
        self.events[request.event_id] = (request.payload_hash(), status)

    async def fail_event(self, request, error, max_attempts):
        attempts = self.attempts.get(request.event_id, 0) + 1
        self.attempts[request.event_id] = attempts
        status = "dead_letter" if attempts >= max_attempts else "retry"
        self.events[request.event_id] = (request.payload_hash(), status)
        return status

    async def approve(self, integration_uuid, actor, correlation_id):
        design = self.designs.get(integration_uuid)
        if not design:
            raise DesignConflict("design revision missing or immutable")
        approved = replace(design, approval_state="approved")
        self.designs[integration_uuid] = approved
        return approved


def request(**changes):
    values = {
        "event_id": f"odoo-event-{uuid4()}",
        "integration_uuid": str(uuid4()),
        "odoo_campaign_id": 910001,
        "environment": "staging",
        "business_unit": "TEST",
        "purpose": "E2E",
        "direction": "outbound",
        "owner_user_id": 9101,
        "supervisor_user_id": 9102,
        "correlation_id": f"correlation-{uuid4()}",
    }
    values.update(changes)
    return CampaignDesignInput(**values)


@pytest.mark.asyncio
async def test_one_odoo_event_produces_one_disabled_design():
    store = MemoryStore()
    item = request()
    result = await CampaignDesignService(store).consume(item)
    assert len(store.designs) == len(store.events) == 1
    assert result["vicidial"]["active"] is False
    assert result["n8n"]["workflows_active"] is False
    assert set(result["feature_flags"].values()) == {False}
    assert result["lifecycle"]["state"] == "approval_pending"


@pytest.mark.asyncio
async def test_event_replay_is_idempotent():
    store = MemoryStore()
    item = request()
    first = await CampaignDesignService(store).consume(item)
    second = await CampaignDesignService(store).consume(item)
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert len(store.designs) == 1


@pytest.mark.asyncio
async def test_changed_payload_conflicts_for_event_and_integration_identity():
    store = MemoryStore()
    item = request()
    await CampaignDesignService(store).consume(item)
    with pytest.raises(DesignConflict, match="event replay payload conflict"):
        await CampaignDesignService(store).consume(
            item.model_copy(update={"purpose": "OTHER"})
        )
    with pytest.raises(DesignConflict, match="integration UUID payload conflict"):
        await CampaignDesignService(store).consume(
            item.model_copy(update={"event_id": "odoo-event-replacement", "purpose": "OTHER"})
        )


@pytest.mark.asyncio
async def test_failed_event_retries_then_dead_letters():
    store = MemoryStore()
    store.fail_create = True
    item = request()
    service = CampaignDesignService(store)
    for expected in ("retry", "retry", "dead_letter"):
        with pytest.raises(RuntimeError):
            await service.consume(item, max_attempts=3)
        assert store.events[item.event_id][1] == expected


@pytest.mark.asyncio
async def test_allocation_is_unique_and_business_unit_isolated():
    store = MemoryStore()
    service = CampaignDesignService(store)
    test_one = await service.consume(request())
    test_two = await service.consume(request())
    cod = await service.consume(request(business_unit="COD"))
    assert {test_one["vicidial"]["default_list_id"],
            test_two["vicidial"]["default_list_id"]} == {91000, 91001}
    assert cod["vicidial"]["default_list_id"] == 21000


@pytest.mark.asyncio
async def test_approval_is_separate_and_never_authorizes_provisioning():
    store = MemoryStore()
    item = request()
    preview = await CampaignDesignService(store).consume(item)
    assert preview["approval"]["state"] == "preview"
    approved = await CampaignDesignService(store).approve(
        item.integration_uuid, "staging-supervisor", item.correlation_id
    )
    assert approved["approval"]["state"] == "approved"
    assert approved["approval"]["provisioning_authorized"] is False
    assert approved["lifecycle"]["state"] == "approved"
    assert approved["lifecycle"]["next_state"] == "provisioning_pending"
    assert approved["lifecycle"]["adapter_delivery_enabled"] is False


def test_authenticated_api_contract_and_production_flags_fail_closed():
    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/campaign-designs/preview"]
    assert "post" in paths[
        "/api/v1/campaign-designs/{integration_uuid}/approve"
    ]
    assert settings.campaign_design_enabled is False
    assert settings.vicidial_write_enabled is False
    assert settings.vicidial_provisioning_enabled is False
    assert settings.n8n_production_workflows_enabled is False
    assert settings.messaging_enabled is False
