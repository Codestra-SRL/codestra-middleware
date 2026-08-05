import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.workers.enterprise_events import (
    claim_deliveries,
    fail_delivery,
    materialize_deliveries,
)


def test_enterprise_delivery_concurrency_restart_and_dead_letter():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert any(marker in database_url for marker in ("enterprise", "rehearsal"))
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    asyncio.run(_scenario(database_url))


async def _scenario(database_url: str):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    tenant_id, workspace_id = uuid4(), uuid4()
    subscription_id, event_id = uuid4(), uuid4()
    try:
        async with factory() as db:
            await db.execute(text("TRUNCATE enterprise_event_delivery, enterprise_event_subscription, enterprise_event CASCADE"))
            await db.execute(
                text("""INSERT INTO enterprise_event_subscription
                    (id,tenant_id,workspace_id,subscriber_key,event_type_pattern,endpoint_key,enabled,max_attempts,created_by)
                    VALUES (:id,:tenant,:workspace,'synthetic','customer.*','mock-sink',true,2,'test')"""),
                {"id": subscription_id, "tenant": tenant_id, "workspace": workspace_id},
            )
            await db.execute(
                text("""INSERT INTO enterprise_event
                    (id,event_id,tenant_id,workspace_id,aggregate_type,aggregate_id,aggregate_sequence,event_type,
                     schema_version,payload,metadata,idempotency_key_hash,correlation_id,occurred_at,recorded_by)
                    VALUES (:id,'evt-1',:tenant,:workspace,'customer','customer-1',1,'customer.created',
                            '1.0','{}'::jsonb,'{}'::jsonb,:key,'corr-1',:now,'test')"""),
                {"id": event_id, "tenant": tenant_id, "workspace": workspace_id, "key": "a" * 64, "now": datetime.now(UTC)},
            )
            await db.commit()
            assert await materialize_deliveries(db, event_id) == 1

        async with factory() as first, factory() as second:
            first_claim, second_claim = await asyncio.gather(
                claim_deliveries(first, worker_id="worker-1"),
                claim_deliveries(second, worker_id="worker-2"),
            )
            assert len(first_claim) + len(second_claim) == 1
            claim = (first_claim or second_claim)[0]
            owner = "worker-1" if first_claim else "worker-2"
            assert await fail_delivery(
                first if first_claim else second,
                UUID(str(claim["id"])),
                owner,
                "TEMPORARY",
                2,
            ) == "RETRY"

        await engine.dispose()
        engine = create_async_engine(database_url)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as restarted:
            await restarted.execute(text("UPDATE enterprise_event_delivery SET next_attempt_at=now()"))
            await restarted.commit()
            claim = (await claim_deliveries(restarted, worker_id="worker-after-restart"))[0]
            assert await fail_delivery(
                restarted,
                UUID(str(claim["id"])),
                "worker-after-restart",
                "TEMPORARY",
                2,
            ) == "DEAD_LETTER"
            assert (await claim_deliveries(restarted, worker_id="worker-3")) == []
    finally:
        await engine.dispose()
