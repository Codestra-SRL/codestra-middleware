from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.campaign_design import (
    CampaignDesignInput,
    CampaignDesignService,
    DesignConflict,
    StoredApproval,
    StoredDesign,
    build_manifest,
    manifest_hash,
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
        self.approvals = {}
        self.revisions = {}

    async def consume_atomic(self, request):
        prior = self.events.get(request.event_id)
        if prior:
            if prior[0] != request.payload_hash():
                raise DesignConflict("event replay payload conflict")
            return prior[1], True
        if self.fail_create:
            raise RuntimeError("synthetic dependency failure")
        existing = self.designs.get(request.integration_uuid)
        if existing:
            if existing.payload_hash == request.payload_hash():
                self.events[request.event_id] = (request.payload_hash(), existing)
                return existing, True
            if existing.approval_state != "approved":
                raise DesignConflict("integration UUID payload conflict")
        revision = existing.revision + 1 if existing else 1
        low = 91000 if request.business_unit == "TEST" else {
            "MOY": 11000, "COD": 21000,
        }.get(request.business_unit, 31000)
        used = self.allocations.setdefault(
            (request.environment, request.business_unit), set()
        )
        list_id = next(item for item in range(low, low + 1000) if item not in used)
        used.add(list_id)
        manifest = build_manifest(request, revision, list_id)
        stored = StoredDesign(
            revision,
            manifest,
            request.payload_hash(),
            manifest_hash(manifest),
            "preview",
        )
        self.designs[request.integration_uuid] = stored
        self.revisions[(request.integration_uuid, revision)] = stored
        self.events[request.event_id] = (request.payload_hash(), stored)
        return stored, False

    async def record_failure(self, request, error, max_attempts):
        attempts = self.attempts.get(request.event_id, 0) + 1
        self.attempts[request.event_id] = attempts
        return "dead_letter" if attempts >= max_attempts else "retry"

    async def approve(
        self,
        integration_uuid,
        revision,
        expected_manifest_hash,
        actor,
        reason,
        idempotency_key,
        correlation_id,
    ):
        replay = self.approvals.get(idempotency_key)
        if replay:
            expected = (
                integration_uuid,
                revision,
                expected_manifest_hash,
                actor,
                reason,
                correlation_id,
            )
            actual = (
                replay.integration_uuid,
                replay.design_revision,
                replay.manifest_hash,
                replay.approver_subject,
                replay.reason,
                replay.correlation_id,
            )
            if actual != expected:
                raise DesignConflict("approval idempotency payload conflict")
            return self.revisions[(integration_uuid, revision)], replay
        design = self.designs.get(integration_uuid)
        if (
            not design
            or design.revision != revision
            or design.manifest_hash != expected_manifest_hash
        ):
            raise DesignConflict("design revision missing or immutable")
        if design.approval_state != "preview":
            raise DesignConflict("design revision already approved")
        approved = StoredDesign(
            design.revision,
            design.manifest,
            design.payload_hash,
            design.manifest_hash,
            "approved",
        )
        approval = StoredApproval(
            str(uuid4()),
            integration_uuid,
            revision,
            expected_manifest_hash,
            actor,
            reason,
            datetime.now(UTC),
            idempotency_key,
            correlation_id,
        )
        self.designs[integration_uuid] = approved
        self.revisions[(integration_uuid, revision)] = approved
        self.approvals[idempotency_key] = approval
        return approved, approval


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
    for expected_attempts in (1, 2, 3):
        with pytest.raises(RuntimeError):
            await service.consume(item, max_attempts=3)
        assert store.attempts[item.event_id] == expected_attempts
    assert item.event_id not in store.events


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
        item.integration_uuid,
        preview["design_revision"],
        store.designs[item.integration_uuid].manifest_hash,
        "staging-supervisor",
        "approved for staging design verification",
        "approval-key-0001",
        item.correlation_id,
    )
    assert approved["approval"]["state"] == "approved"
    assert approved["approval"]["provisioning_authorized"] is False
    assert approved["lifecycle"]["state"] == "approved"
    assert approved["lifecycle"]["next_state"] == "provisioning_pending"
    assert approved["lifecycle"]["adapter_delivery_enabled"] is False


@pytest.mark.asyncio
async def test_approval_replay_preserves_original_provenance():
    store = MemoryStore()
    item = request()
    preview = await CampaignDesignService(store).consume(item)
    digest = store.designs[item.integration_uuid].manifest_hash
    service = CampaignDesignService(store)
    first = await service.approve(
        item.integration_uuid,
        1,
        digest,
        "staging-supervisor",
        "approved for staging design verification",
        "approval-key-replay",
        item.correlation_id,
    )
    second = await service.approve(
        item.integration_uuid,
        1,
        digest,
        "staging-supervisor",
        "approved for staging design verification",
        "approval-key-replay",
        item.correlation_id,
    )
    assert first["approval"] == second["approval"]
    assert len(store.approvals) == 1
    assert preview["approval"]["state"] == "preview"


@pytest.mark.asyncio
async def test_approval_cannot_replace_actor_reason_or_manifest():
    store = MemoryStore()
    item = request()
    await CampaignDesignService(store).consume(item)
    digest = store.designs[item.integration_uuid].manifest_hash
    service = CampaignDesignService(store)
    await service.approve(
        item.integration_uuid,
        1,
        digest,
        "staging-supervisor",
        "approved for staging design verification",
        "approval-key-conflict",
        item.correlation_id,
    )
    with pytest.raises(DesignConflict):
        await service.approve(
            item.integration_uuid,
            1,
            digest,
            "another-supervisor",
            "different approval reason",
            "approval-key-conflict",
            item.correlation_id,
        )


def test_authenticated_api_contract_and_production_flags_fail_closed():
    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/campaign-designs/preview"]
    assert "post" in paths[
        "/api/v1/campaign-designs/{integration_uuid}/approve"
    ]
    approval_parameters = paths[
        "/api/v1/campaign-designs/{integration_uuid}/approve"
    ]["post"]["parameters"]
    header_names = {
        parameter["name"]
        for parameter in approval_parameters
        if parameter["in"] == "header"
    }
    assert "Authorization" in header_names
    assert "X-Approval-Actor" not in header_names
    assert settings.campaign_design_enabled is False
    assert settings.vicidial_write_enabled is False
    assert settings.vicidial_provisioning_enabled is False
    assert settings.n8n_production_workflows_enabled is False
    assert settings.messaging_enabled is False
