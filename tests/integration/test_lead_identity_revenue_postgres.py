import asyncio
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from fastapi.testclient import TestClient

from app.leads.domain import normalize_email
from app.leads.repository import LeadRepository

DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="TEST_DATABASE_URL is required"
)


def test_concurrent_identity_resolution_revenue_dedupe_and_attribution():
    async def scenario():
        engine = create_async_engine(DATABASE_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tenant_id, campaign_a, campaign_b = uuid4(), uuid4(), uuid4()
        email = normalize_email("same.person@example.com")

        async def resolve():
            async with factory() as session:
                return await LeadRepository(session).resolve_person(
                    tenant_id=tenant_id,
                    display_name="Synthetic Person",
                    email=email,
                    phone=None,
                    social=None,
                    correlation_id=str(uuid4()),
                )

        first, second = await asyncio.gather(resolve(), resolve())
        assert first["person_id"] == second["person_id"]
        async with factory() as session:
            assert (
                await session.execute(
                    text(
                        "SELECT count(*) FROM person_identities WHERE tenant_id=:tenant"
                    ),
                    {"tenant": tenant_id},
                )
            ).scalar_one() == 1
            assert (
                await session.execute(
                    text("SELECT count(*) FROM contact_points WHERE tenant_id=:tenant"),
                    {"tenant": tenant_id},
                )
            ).scalar_one() == 1
            repository = LeadRepository(session)
            company = await repository.resolve_company(
                tenant_id=tenant_id,
                legal_name="Synthetic Example Ltd",
                display_name="Synthetic Example",
                domain="example.test",
                registration_number=None,
                country="GB",
                correlation_id="company-correlation",
            )
            company_duplicate = await repository.resolve_company(
                tenant_id=tenant_id,
                legal_name="Synthetic Example Ltd",
                display_name="Synthetic Example",
                domain="example.test",
                registration_number=None,
                country="GB",
                correlation_id="company-correlation-2",
            )
            assert (
                company["company_id"] == company_duplicate["company_id"]
                and not company_duplicate["created"]
            )
            lead_id, lead_created = await repository.upsert_lead(
                tenant_id=tenant_id,
                person_id=first["person_id"],
                company_id=None,
                campaign_id=campaign_a,
                source="SYNTHETIC",
                consent="GRANTED",
                dnc="CLEAR",
            )
            duplicate_lead_id, duplicate_created = await repository.upsert_lead(
                tenant_id=tenant_id,
                person_id=first["person_id"],
                company_id=None,
                campaign_id=campaign_a,
                source="SYNTHETIC",
                consent="GRANTED",
                dnc="CLEAR",
            )
            assert (
                lead_created and not duplicate_created and duplicate_lead_id == lead_id
            )
            for index in range(10):
                _, interaction_created = await repository.add_interaction(
                    tenant_id=tenant_id,
                    lead_id=lead_id,
                    interaction_type="SOCIAL_MESSAGE",
                    source="SYNTHETIC",
                    source_event_id=f"message-{index}",
                    campaign_id=campaign_a,
                    content_id=None,
                    correlation_id=f"corr-{index}",
                    occurred_at=datetime.now(timezone.utc),
                    safe_payload={"classification": "PUBLIC_OBSERVATION"},
                )
                assert interaction_created
            assert (
                await session.execute(
                    text("SELECT count(*) FROM lead_interactions WHERE lead_id=:lead"),
                    {"lead": lead_id},
                )
            ).scalar_one() == 10
            now = datetime.now(timezone.utc)
            for index, campaign in enumerate((campaign_a, campaign_b)):
                await session.execute(
                    text(
                        "INSERT INTO lead_campaign_touches(id,tenant_id,lead_id,campaign_id,source,event_type,source_event_id,occurred_at) VALUES(:id,:tenant,:lead,:campaign,'SYNTHETIC','CAMPAIGN_TOUCH',:event,:occurred)"
                    ),
                    {
                        "id": uuid4(),
                        "tenant": tenant_id,
                        "lead": lead_id,
                        "campaign": campaign,
                        "event": f"touch-{index}",
                        "occurred": now - timedelta(days=2 - index),
                    },
                )
            await session.commit()
            event_id, created = await repository.create_revenue(
                tenant_id=tenant_id,
                lead_id=lead_id,
                event_type="SALE_WON",
                amount=Decimal("1000"),
                currency="USD",
                source_system="SYNTHETIC_ODOO",
                external_reference="SALE-1",
                occurred_at=now,
            )
            duplicate_id, duplicate_created = await repository.create_revenue(
                tenant_id=tenant_id,
                lead_id=lead_id,
                event_type="SALE_WON",
                amount=Decimal("1000"),
                currency="USD",
                source_system="SYNTHETIC_ODOO",
                external_reference="SALE-1",
                occurred_at=now,
            )
            assert event_id == duplicate_id and created and not duplicate_created
            for model in (
                "FIRST_TOUCH",
                "LAST_TOUCH",
                "LINEAR",
                "POSITION_BASED",
                "TIME_DECAY",
            ):
                result = await repository.calculate_attribution(
                    tenant_id=tenant_id, revenue_event_id=event_id, model=model
                )
                assert sum(item["weight"] for item in result["allocations"]) == Decimal(
                    1
                )
                assert sum(
                    item["attributed_amount"] for item in result["allocations"]
                ) == Decimal("1000")
            assert (
                await session.execute(
                    text("SELECT count(*) FROM revenue_events WHERE tenant_id=:tenant"),
                    {"tenant": tenant_id},
                )
            ).scalar_one() == 1
        await engine.dispose()

    asyncio.run(scenario())


def test_n7_api_is_tenant_scoped_fail_closed_and_dry_run(monkeypatch):
    from app.core.config import settings
    from app.db.session import get_session
    from app.main import app

    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with factory() as session:
            yield session

    monkeypatch.setattr(settings, "middleware_secret", "synthetic-bearer")
    monkeypatch.setattr(settings, "identity_graph_enabled", True)
    monkeypatch.setattr(settings, "lead_intelligence_enabled", True)
    monkeypatch.setattr(settings, "next_best_action_enabled", True)
    app.dependency_overrides[get_session] = session_override
    client = TestClient(app)
    tenant_id = str(uuid4())
    headers = {
        "Authorization": "Bearer synthetic-bearer",
        "X-Codestra-Permissions": "identity.review,identity.read,lead.write,lead.read,lead.score",
    }
    identity = client.post(
        "/api/v1/identity/resolve",
        headers=headers,
        json={
            "tenant_id": tenant_id,
            "display_name": "Synthetic API Person",
            "email": "api@example.test",
        },
    )
    assert identity.status_code == 200
    person_id = identity.json()["person_id"]
    duplicate = client.post(
        "/api/v1/identity/resolve",
        headers=headers,
        json={
            "tenant_id": tenant_id,
            "display_name": "Synthetic API Person",
            "email": "api@example.test",
        },
    )
    assert (
        duplicate.json()["person_id"] == person_id and not duplicate.json()["created"]
    )
    lead = client.post(
        "/api/v1/leads",
        headers=headers,
        json={
            "tenant_id": tenant_id,
            "person_id": person_id,
            "source": "SYNTHETIC",
            "consent_status": "UNKNOWN",
            "dnc_status": "CLEAR",
        },
    )
    assert lead.status_code == 201 and not lead.json()["external_command_dispatched"]
    lead_id = lead.json()["lead_id"]
    action = client.post(
        f"/api/v1/leads/{lead_id}/next-action",
        headers=headers,
        json={
            "tenant_id": tenant_id,
            "intent": "BUYING_INTENT",
            "score_components": {"intent_quality": 25, "contactability": 15},
            "has_phone": True,
        },
    )
    assert action.status_code == 200
    assert action.json()["action"] == "MANUAL_REVIEW"
    assert (
        not action.json()["eligible_for_contact"]
        and not action.json()["automatic_contact"]
    )
    wrong_tenant = client.get(
        f"/api/v1/identity/persons/{person_id}?tenant_id={uuid4()}", headers=headers
    )
    assert wrong_tenant.status_code == 404
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
