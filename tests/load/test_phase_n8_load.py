import asyncio
import os
import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.leads.repository import LeadRepository

DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL or os.getenv("RUN_N8_LOAD") != "true",
    reason="explicit disposable Phase N8 load environment is required",
)


def test_bounded_synthetic_n8_load():
    async def scenario():
        started = time.perf_counter()
        engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=5)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tenant_id, campaign_id = uuid4(), uuid4()
        person_ids = []

        async with factory() as session:
            repository = LeadRepository(session)
            for index in range(1000):
                identity = await repository.resolve_person(
                    tenant_id=tenant_id,
                    display_name=f"Synthetic Load {index}",
                    email=f"synthetic-load-{index}@example.invalid",
                    phone=None,
                    social=None,
                    correlation_id=f"n8-load-{index}",
                )
                person_ids.append(identity["person_id"])
                lead_id, created = await repository.upsert_lead(
                    tenant_id=tenant_id,
                    person_id=identity["person_id"],
                    company_id=None,
                    campaign_id=campaign_id,
                    source="SYNTHETIC_LOAD",
                    consent="UNKNOWN",
                    dnc="CLEAR",
                )
                assert created and lead_id

            for index in range(1000):
                replay = await repository.resolve_person(
                    tenant_id=tenant_id,
                    display_name=f"Synthetic Load {index}",
                    email=f"synthetic-load-{index}@example.invalid",
                    phone=None,
                    social=None,
                    correlation_id=f"n8-load-replay-{index}",
                )
                assert replay["person_id"] == person_ids[index]
                assert not replay["created"]

            leads = (
                (
                    await session.execute(
                        text(
                            "SELECT id,person_id FROM lead_records WHERE tenant_id=:tenant ORDER BY id"
                        ),
                        {"tenant": tenant_id},
                    )
                )
                .mappings()
                .all()
            )
            for index, lead in enumerate(leads[:500]):
                _, created = await repository.add_interaction(
                    tenant_id=tenant_id,
                    lead_id=lead["id"],
                    interaction_type="FORM_SUBMISSION",
                    source="SYNTHETIC_WEBSITE",
                    source_event_id=f"second-source-{index}",
                    campaign_id=campaign_id,
                    content_id=None,
                    correlation_id=f"n8-load-second-{index}",
                    occurred_at=datetime.now(UTC),
                    safe_payload={"synthetic": True},
                )
                assert created

            models = (
                "FIRST_TOUCH",
                "LAST_TOUCH",
                "LINEAR",
                "POSITION_BASED",
                "TIME_DECAY",
            )
            for index, lead in enumerate(leads[:100]):
                now = datetime.now(UTC)
                await session.execute(
                    text(
                        "INSERT INTO lead_campaign_touches(id,tenant_id,lead_id,campaign_id,source,event_type,source_event_id,occurred_at) VALUES(:id,:tenant,:lead,:campaign,'SYNTHETIC_LOAD','CAMPAIGN_TOUCH',:event,:occurred)"
                    ),
                    {
                        "id": uuid4(),
                        "tenant": tenant_id,
                        "lead": lead["id"],
                        "campaign": campaign_id,
                        "event": f"load-touch-{index}",
                        "occurred": now,
                    },
                )
                await session.commit()
                revenue_id, created = await repository.create_revenue(
                    tenant_id=tenant_id,
                    lead_id=lead["id"],
                    event_type="PAYMENT_RECEIVED",
                    amount=Decimal("1000"),
                    currency="USD",
                    source_system="SYNTHETIC_LOAD",
                    external_reference=f"load-revenue-{index}",
                    occurred_at=now,
                    is_synthetic=True,
                )
                assert created
                for model in models:
                    result = await repository.calculate_attribution(
                        tenant_id=tenant_id,
                        revenue_event_id=revenue_id,
                        model=model,
                    )
                    assert sum(
                        item["weight"] for item in result["allocations"]
                    ) == Decimal(1)

            counts = (
                (
                    await session.execute(
                        text(
                            "SELECT (SELECT count(*) FROM person_identities WHERE tenant_id=:tenant) persons,(SELECT count(*) FROM lead_records WHERE tenant_id=:tenant) leads,(SELECT count(*) FROM revenue_events WHERE tenant_id=:tenant) revenue"
                        ),
                        {"tenant": tenant_id},
                    )
                )
                .mappings()
                .one()
            )
            assert counts == {"persons": 1000, "leads": 1000, "revenue": 100}
            print(
                f"N8_LOAD elapsed_seconds={time.perf_counter() - started:.3f} "
                "unique=1000 replays=1000 second_source=500 "
                "attributions=500 revenue=100 duplicates=0"
            )
        await engine.dispose()

    asyncio.run(scenario())
