import os
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1 import odoo_business as api
from app.core.iam import IdentityContext
from app.core.odoo_business import BusinessCommand, OdooBusinessError, RESOURCE_TYPES
from app.core.odoo_services import SERVICES
from app.db.session import SessionFactory
from app.main import OIDC_BUSINESS_PATH
from app.workers.odoo_business import (
    claim_commands,
    complete_command,
    fail_command,
    recover_expired_leases,
)


def identity(tenant: UUID, workspace: UUID, subject: str = "synthetic-operator") -> IdentityContext:
    return IdentityContext(
        subject=subject,
        tenant_id=str(tenant),
        workspace_id=str(workspace),
        department_ids=frozenset(),
        roles=frozenset({"platform_owner"}),
        permissions=frozenset({"*"}),
        session_id="synthetic-session",
    )


def test_resource_contract_covers_wave3_and_rejects_privileged_fields():
    assert len(RESOURCE_TYPES) == 25
    for required in ("customer", "lead", "appointment", "project", "support_ticket",
                     "recording", "ai_employee", "marketplace_listing", "subscription",
                     "usage_record", "knowledge_article", "audit_record"):
        assert required in RESOURCE_TYPES
    with pytest.raises(OdooBusinessError, match="privileged"):
        BusinessCommand("lead", "create", "lead-001", {"model": "crm.lead"}).validate()
    with pytest.raises(OdooBusinessError, match="privileged"):
        BusinessCommand("lead", "create", "lead-001", {"access_token": "fixture"}).validate()
    assert {service.name for service in SERVICES} == {
        "customer", "lead", "activity", "project", "appointment", "support",
        "voice", "ai", "marketplace", "commercial", "usage", "audit",
    }
    assert set().union(*(service.resource_types for service in SERVICES)) == set(RESOURCE_TYPES)


@pytest.mark.asyncio
async def test_business_routes_fail_closed_without_validated_oidc():
    assert OIDC_BUSINESS_PATH.fullmatch("/api/v1/business/commands")
    assert OIDC_BUSINESS_PATH.fullmatch(
        "/api/v1/business/commands/00000000-0000-0000-0000-000000000001/approval"
    )
    assert not OIDC_BUSINESS_PATH.fullmatch("/api/v1/business/commands/arbitrary")
    assert not OIDC_BUSINESS_PATH.fullmatch("/api/v1/business/admin")
    app = FastAPI()
    app.include_router(api.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/business/resource-types")
    assert response.status_code == 401
    assert response.json() == {"detail": "bearer authorization required"}


@pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="disposable PostgreSQL required")
@pytest.mark.asyncio
async def test_durable_command_tenant_idempotency_approval_worker_and_reconciliation(monkeypatch):
    tenant, workspace, other_tenant, other_workspace = uuid4(), uuid4(), uuid4(), uuid4()
    async with SessionFactory() as db:
        await db.execute(text("TRUNCATE odoo_business_audit,odoo_business_reconciliation,odoo_business_reference,odoo_business_command CASCADE"))
        await db.execute(text("""
            INSERT INTO iam_tenant (id,slug,display_name,status,created_by,updated_by,version,audit_id)
            VALUES (:t,:tenant_slug,'Wave 3 Synthetic','ACTIVE','fixture','fixture',1,gen_random_uuid()),
                   (:ot,:other_slug,'Wave 3 Other','ACTIVE','fixture','fixture',1,gen_random_uuid())
            ON CONFLICT (id) DO NOTHING
        """), {"t": tenant, "ot": other_tenant, "tenant_slug": f"wave3-{tenant.hex}",
                 "other_slug": f"wave3-{other_tenant.hex}"})
        await db.execute(text("""
            INSERT INTO iam_workspace (id,tenant_id,workspace_id,slug,display_name,created_by,updated_by,version,audit_id)
            VALUES (:w,:t,:w,'primary','Synthetic','fixture','fixture',1,gen_random_uuid()),
                   (:ow,:ot,:ow,'other','Other','fixture','fixture',1,gen_random_uuid())
            ON CONFLICT (id) DO NOTHING
        """), {"w": workspace, "t": tenant, "ow": other_workspace, "ot": other_tenant})
        await db.commit()

    current = identity(tenant, workspace)
    monkeypatch.setattr(api, "_identity", lambda _authorization: current)
    app = FastAPI()
    app.include_router(api.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        headers = {
            "Authorization": "Bearer synthetic",
            "Idempotency-Key": "fixture-wave3-key-0001",
            "X-Correlation-ID": "corr-wave3-001",
        }
        body = {
            "resource_type": "lead", "operation": "create", "resource_key": "lead-001",
            "payload": {"full_name": "Synthetic Person", "email": "person@example.invalid"},
        }
        created = await client.post("/api/v1/business/commands", json=body, headers=headers)
        assert created.status_code == 202
        assert created.json()["delivery_mode"] == "DISABLED"
        duplicate = await client.post("/api/v1/business/commands", json=body, headers=headers)
        assert duplicate.status_code == 202 and duplicate.json()["idempotent_replay"]
        conflict = await client.post(
            "/api/v1/business/commands", json={**body, "payload": {"full_name": "Different"}}, headers=headers
        )
        assert conflict.status_code == 409
        command_id = created.json()["command_id"]

        current = identity(other_tenant, other_workspace)
        isolated = await client.get(
            f"/api/v1/business/commands/{command_id}", headers={"Authorization": "Bearer synthetic"}
        )
        assert isolated.status_code == 404
        current = identity(tenant, workspace)

        approval_body = {
            "resource_type": "project", "operation": "transition", "resource_key": "project-001",
            "payload": {"target_state": "approved"},
        }
        approval_headers = {**headers, "Idempotency-Key": "fixture-wave3-key-0002"}
        pending = await client.post("/api/v1/business/commands", json=approval_body, headers=approval_headers)
        assert pending.json()["approval_state"] == "PENDING"
        approved = await client.post(
            f"/api/v1/business/commands/{pending.json()['command_id']}/approval",
            json={"decision": "APPROVED", "reason": "Synthetic approval evidence"}, headers=headers,
        )
        assert approved.status_code == 200 and approved.json()["state"] == "READY"

        reconciliation = await client.post(
            "/api/v1/business/reconciliations",
            json={"resource_type": "lead", "resource_key": "lead-001"}, headers=headers,
        )
        assert reconciliation.status_code == 202
        assert not reconciliation.json()["external_read_enabled"]

    async with SessionFactory() as db:
        assert await claim_commands(db, worker_id="worker-disabled") == []
        await db.execute(text("UPDATE odoo_business_command SET delivery_mode='MOCK' WHERE public_id=:id"),
                         {"id": UUID(command_id)})
        await db.commit()
        claimed = await claim_commands(db, worker_id="worker-a", delivery_enabled=True)
        assert len(claimed) == 1
        assert await claim_commands(db, worker_id="worker-b", delivery_enabled=True) == []
        item = claimed[0]
        assert await complete_command(
            db, item["id"], "worker-a", item["fencing_token"],
            remote_model="mock.lead", remote_id=101, remote_version="synthetic-v1",
        )
        assert not await complete_command(
            db, item["id"], "worker-a", item["fencing_token"],
            remote_model="mock.lead", remote_id=101, remote_version="synthetic-v1",
        )
        reference_count = (await db.execute(text("SELECT count(*) FROM odoo_business_reference"))).scalar_one()
        assert reference_count == 1

        approved_internal = (await db.execute(text(
            "SELECT id FROM odoo_business_command WHERE public_id=:id"
        ), {"id": UUID(pending.json()["command_id"])})).scalar_one()
        await db.execute(text("UPDATE odoo_business_command SET delivery_mode='MOCK' WHERE id=:id"),
                         {"id": approved_internal})
        await db.commit()
        retried_item = (await claim_commands(db, worker_id="worker-a", delivery_enabled=True))[0]
        assert await fail_command(db, retried_item["id"], "worker-a", retried_item["fencing_token"],
                                  "SYNTHETIC_TIMEOUT", retryable=True) == "RETRY_WAIT"
        await db.execute(text("UPDATE odoo_business_command SET next_attempt_at=now(),max_attempts=2 WHERE id=:id"),
                         {"id": retried_item["id"]})
        await db.commit()
        final_item = (await claim_commands(db, worker_id="worker-b", delivery_enabled=True))[0]
        assert await fail_command(db, final_item["id"], "worker-b", final_item["fencing_token"],
                                  "SYNTHETIC_PERMANENT", retryable=False) == "DEAD_LETTER"

        await db.execute(text("""
            UPDATE odoo_business_command SET state='LEASED',delivery_mode='MOCK',lease_owner='expired',
                lease_expires_at=now()-interval '1 second',attempt_count=max_attempts
            WHERE id=:id
        """), {"id": retried_item["id"]})
        await db.commit()
        assert (await recover_expired_leases(db))["dead_lettered"] == 1

        with pytest.raises(Exception, match="append-only"):
            await db.execute(text("UPDATE odoo_business_audit SET action='MUTATED'"))
            await db.commit()
        await db.rollback()
