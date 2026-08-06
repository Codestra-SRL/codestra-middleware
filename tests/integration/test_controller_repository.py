import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import httpx
from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1 import controller as controller_api
from app.entrypoints.controller_api import app as controller_app
from app.core.controller import ControllerError
from app.core.controller_repository import PostgresControllerRepository
from app.db.session import SessionFactory, engine


pytestmark = pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="disposable PostgreSQL required")


@pytest.mark.asyncio
async def test_persistence_idempotency_audit_approval_verification_and_tenant_isolation():
    tenant = "tenant-repository-fixture"
    body = {"workspace": "/opt/codestra/worktrees/fixture", "title": "fixture", "objective": "fixture"}
    async with SessionFactory() as session:
        await session.execute(text("TRUNCATE controller_verifications,controller_executions,controller_task_audit,controller_approvals,controller_tasks"))
        await session.commit()
        repo = PostgresControllerRepository(session)
        row, replay = await repo.create_task(body, tenant_id=tenant, request_id="request-1",
                                             correlation_id="correlation-1", idempotency_key="fixture-key")
        assert not replay
        repeated, replay = await repo.create_task(body, tenant_id=tenant, request_id="request-2",
                                                  correlation_id="correlation-2", idempotency_key="fixture-key")
        assert replay and repeated["id"] == row["id"]
        audit = (await session.execute(text("SELECT * FROM controller_task_audit WHERE task_id=:id"),
                                       {"id": row["id"]})).mappings().all()
        assert len(audit) == 1 and audit[0]["previous_hash"] == "0" * 64
        await repo.save_approval(task_id=row["id"], tenant_id=tenant, plan_hash="a" * 64,
                                 server_id="web", tools=["git_status"], approver="fixture-reviewer",
                                 jti="fixture-jti", expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
        await repo.consume_approval("fixture-jti", row["id"], tenant)
        with pytest.raises(ControllerError, match="replay"):
            await repo.consume_approval("fixture-jti", row["id"], tenant)
        execution_id = uuid4()
        await session.execute(text("""INSERT INTO controller_executions
          (id,task_id,tenant_id,server_id,workspace,tool,request_id,correlation_id,evidence_hash)
          VALUES (:id,:task,:tenant,'web','/fixture','git_status','request','correlation',:evidence)"""),
          {"id": execution_id, "task": row["id"], "tenant": tenant, "evidence": "b" * 64})
        await session.commit()
        verification = {"verification_code": "VRF-fixture-repository", "task_id": row["id"],
                        "execution_id": execution_id, "tenant_id": tenant, "checks": {"UNIT_TESTS": "PASS"},
                        "evidence_hash": "b" * 64, "signature": "fixture-signature"}
        await repo.save_verification(verification)
        hidden = await session.scalar(text("SELECT count(*) FROM controller_tasks WHERE id=:id AND tenant_id=:tenant"),
                                      {"id": row["id"], "tenant": "other"})
        assert hidden == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_skip_locked_claim_versioned_heartbeat_and_expiry_recovery():
    task_id = uuid4()
    async with SessionFactory() as setup:
        await setup.execute(text("""INSERT INTO controller_tasks
          (id,tenant_id,workspace,title,objective,request_id,correlation_id,idempotency_key_hash,
           request_hash,state,available_at,max_attempts)
          VALUES (:id,'tenant-claim','/fixture','fixture','fixture','request','correlation',:key,:request,'QUEUED',now(),2)
        """), {"id": task_id, "key": "c" * 64, "request": "d" * 64})
        await setup.commit()
    async with SessionFactory() as one, SessionFactory() as two:
        first = await PostgresControllerRepository(one).claim("web", "worker-one", 30)
        second = await PostgresControllerRepository(two).claim("web", "worker-two", 30)
        assert first and UUID(str(first["id"])) == task_id and second is None
        updated = await PostgresControllerRepository(one).heartbeat(
            task_id, "tenant-claim", "web:worker-one", int(first["version"]), 30)
        assert updated["version"] == first["version"] + 1
        await one.execute(text("UPDATE controller_tasks SET lease_expires_at=now()-interval '1 second' WHERE id=:id"),
                          {"id": task_id})
        await one.commit()
        result = await PostgresControllerRepository(one).recover_expired()
        assert result == {"retried": 1, "dead_lettered": 0}
    await engine.dispose()


@pytest.mark.asyncio
async def test_runtime_api_uses_postgres_and_survives_controller_restart(tmp_path, monkeypatch):
    async with SessionFactory() as cleanup:
        await cleanup.execute(text("TRUNCATE controller_verifications,controller_executions,controller_task_audit,controller_approvals,controller_tasks"))
        await cleanup.commit()
    signing_key = tmp_path / "controller-signing.key"
    signing_key.write_bytes(b"fixture-controller-runtime-signing-material-minimum")
    signing_key.chmod(0o600)
    monkeypatch.setattr(controller_api.settings, "controller_repository_backend", "postgres")
    monkeypatch.setattr(controller_api.settings, "controller_private_enabled", True)
    monkeypatch.setattr(controller_api.settings, "controller_approval_signing_key_file", str(signing_key))
    monkeypatch.setattr(controller_api.settings, "controller_workspace_allowlist", "/workspace")
    controller_api.controller.cache_clear()
    app = FastAPI()
    app.include_router(controller_api.router)
    headers = {"X-Tenant-ID": "tenant-runtime", "X-Request-ID": "request-runtime",
               "X-Correlation-ID": "correlation-runtime", "Idempotency-Key": "fixture-runtime-key"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/api/v1/tasks", headers=headers,
            json={"title": "runtime", "objective": "durability", "workspace": "/workspace"})
        assert created.status_code == 201
        task = created.json()
        replay = await client.post("/api/v1/tasks", headers=headers,
            json={"title": "runtime", "objective": "durability", "workspace": "/workspace"})
        assert replay.json()["task_id"] == task["task_id"] and replay.json()["idempotent_replay"]
        planned = await client.post(f"/api/v1/tasks/{task['task_id']}/plan", headers=headers,
            json={"steps": [{"tool": "git_status", "arguments": {}}]})
        approved = await client.post(f"/api/v1/tasks/{task['task_id']}/approve",
            headers={**headers, "X-Actor-ID": "fixture-reviewer"},
            json={"plan_hash": planned.json()["plan_hash"], "server_id": "middleware"})
        assert approved.status_code == 200
        execution_body = {"task_id": task["task_id"], "server_id": "middleware",
            "workspace": "/workspace", "tool": "git_status", "arguments": {},
            "approval_token": approved.json()["approval_token"]}
        executed = await client.post("/api/v1/tools/execute", headers=headers, json=execution_body)
        assert executed.status_code == 202
        replayed = await client.post("/api/v1/tools/execute", headers=headers, json=execution_body)
        assert replayed.status_code == 401
    controller_api.controller.cache_clear()
    restarted = FastAPI()
    restarted.include_router(controller_api.router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restarted), base_url="http://test") as client:
        persisted = await client.get(f"/api/v1/tasks/{task['task_id']}", headers=headers)
        verification = await client.get(
            f"/api/v1/verifications/{executed.json()['verification_code']}", headers=headers)
        audit = await client.get(f"/api/v1/audit/{task['task_id']}", headers=headers)
        hidden = await client.get(f"/api/v1/tasks/{task['task_id']}",
                                  headers={**headers, "X-Tenant-ID": "tenant-other"})
        assert persisted.status_code == 200 and persisted.json()["state"] == "EXECUTING"
        assert verification.status_code == 200
        assert audit.status_code == 200 and len(audit.json()["records"]) == 4
        assert hidden.status_code == 404
    controller_api.controller.cache_clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_private_readiness_requires_reachable_postgres(tmp_path, monkeypatch):
    signing_key = tmp_path / "controller-signing.key"
    signing_key.write_bytes(b"fixture-controller-readiness-signing-material-minimum")
    signing_key.chmod(0o600)
    monkeypatch.setattr(controller_api.settings, "controller_repository_backend", "postgres")
    monkeypatch.setattr(controller_api.settings, "controller_private_enabled", True)
    monkeypatch.setattr(controller_api.settings, "controller_approval_signing_key_file", str(signing_key))
    controller_api.controller.cache_clear()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=controller_app),
                                 base_url="http://test") as client:
        response = await client.get("/readyz")
        assert response.status_code == 200
    controller_api.controller.cache_clear()
    await engine.dispose()
