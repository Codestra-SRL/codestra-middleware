import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from app.core.controller import ControllerError
from app.core.controller_repository import PostgresControllerRepository
from app.db.session import SessionFactory, engine


pytestmark = pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="disposable PostgreSQL required")


@pytest.mark.asyncio
async def test_persistence_idempotency_audit_approval_verification_and_tenant_isolation():
    tenant = "tenant-repository-fixture"
    body = {"workspace": "/opt/codestra/worktrees/fixture", "title": "fixture", "objective": "fixture"}
    async with SessionFactory() as session:
        await session.execute(text("TRUNCATE controller_verifications,controller_task_audit,controller_approvals,controller_tasks"))
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
        verification = {"verification_code": "VRF-fixture-repository", "task_id": row["id"],
                        "execution_id": uuid4(), "tenant_id": tenant, "checks": {"UNIT_TESTS": "PASS"},
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
