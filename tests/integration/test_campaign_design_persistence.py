import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.campaign_design import (
    CampaignDesignInput, CampaignDesignService, PostgresDesignStore,
)


def test_transactional_event_and_concurrent_list_allocation():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert "diag" in database_url or "rehearsal" in database_url
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    asyncio.run(_scenario(database_url))


def _request(index: int) -> CampaignDesignInput:
    return CampaignDesignInput(
        event_id=f"diag-odoo-event-{uuid4()}",
        integration_uuid=str(uuid4()),
        odoo_campaign_id=910000 + index,
        environment="staging",
        business_unit="TEST",
        purpose=f"E{index:02d}",
        direction="outbound",
        owner_user_id=9101,
        supervisor_user_id=9102,
        correlation_id=f"diag-correlation-{uuid4()}",
    )


async def _scenario(database_url: str):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            await session.execute(text(
                "TRUNCATE campaign_design_event,campaign_list_reservation,"
                "campaign_design_revision"
            ))
            await session.commit()

        # An Odoo transaction that rolls back cannot leave an outbox receipt.
        rolled_back = _request(99)
        async with factory() as session:
            await session.execute(text(
                "INSERT INTO campaign_design_event"
                "(event_id,integration_uuid,payload_hash,status,attempts,correlation_id) "
                "VALUES(:event,:uuid,:hash,'retry',0,:correlation)"
            ), {"event": rolled_back.event_id,
                "uuid": rolled_back.integration_uuid,
                "hash": rolled_back.payload_hash(),
                "correlation": rolled_back.correlation_id})
            await session.rollback()
        async with factory() as session:
            assert await session.scalar(text(
                "SELECT count(*) FROM campaign_design_event WHERE event_id=:event"
            ), {"event": rolled_back.event_id}) == 0

        requests = [_request(index) for index in range(10)]

        async def create(item):
            async with factory() as session:
                return await CampaignDesignService(
                    PostgresDesignStore(session)
                ).consume(item)

        manifests = await asyncio.gather(*(create(item) for item in requests))
        list_ids = [item["vicidial"]["default_list_id"] for item in manifests]
        assert len(list_ids) == len(set(list_ids)) == 10
        assert all(91000 <= item <= 91999 for item in list_ids)
        async with factory() as session:
            assert await session.scalar(text(
                "SELECT count(*) FROM campaign_design_event"
            )) == 10
            assert await session.scalar(text(
                "SELECT count(*) FROM campaign_design_revision"
            )) == 10
    finally:
        await engine.dispose()
