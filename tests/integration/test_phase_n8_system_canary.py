import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.social_platform import OdooDryRunRequest, odoo_dry_run
from app.core.config import settings
from app.leads.domain import NextAction, next_best_action, quality_score
from app.leads.repository import LeadRepository
from app.workers.delivery import recover
from app.workers.social_n8n_delivery import reconcile_terminal, stage_pending

DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="TEST_DATABASE_URL is required"
)


def test_complete_synthetic_business_canary(monkeypatch):
    monkeypatch.setattr(settings, "social_n8n_delivery_batch_size", 8)
    monkeypatch.setattr(settings, "social_n8n_delivery_lease_seconds", 30)

    async def scenario():
        engine = create_async_engine(DATABASE_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tenant_id, campaign_id, content_id = uuid4(), uuid4(), uuid4()
        event_id, correlation_id = str(uuid4()), str(uuid4())
        now = datetime.now(UTC)

        async with factory() as session:
            repository = LeadRepository(session)
            identities = []
            for _ in range(10):
                identities.append(
                    await repository.resolve_person(
                        tenant_id=tenant_id,
                        display_name="Synthetic Customer",
                        email="synthetic-lead@example.invalid",
                        phone="+15555550100",
                        social=("postly", "facebook", "synthetic-profile-n8"),
                        correlation_id=correlation_id,
                    )
                )
            person_id = identities[0]["person_id"]
            assert {item["person_id"] for item in identities} == {person_id}
            assert sum(bool(item["created"]) for item in identities) == 1

            lead_ids = []
            for _ in range(10):
                lead_ids.append(
                    await repository.upsert_lead(
                        tenant_id=tenant_id,
                        person_id=person_id,
                        company_id=None,
                        campaign_id=campaign_id,
                        source="SOCIAL",
                        consent="UNKNOWN",
                        dnc="CLEAR",
                    )
                )
            lead_id = lead_ids[0][0]
            assert {item[0] for item in lead_ids} == {lead_id}
            assert sum(item[1] for item in lead_ids) == 1

            interaction_ids = []
            for _ in range(10):
                interaction_ids.append(
                    await repository.add_interaction(
                        tenant_id=tenant_id,
                        lead_id=lead_id,
                        interaction_type="SOCIAL_MESSAGE",
                        source="postly",
                        source_event_id=event_id,
                        campaign_id=campaign_id,
                        content_id=content_id,
                        correlation_id=correlation_id,
                        occurred_at=now,
                        safe_payload={
                            "intent": "BUYING_INTENT",
                            "message_class": "QUOTE_REQUEST",
                            "synthetic": True,
                        },
                    )
                )
            assert len({item[0] for item in interaction_ids}) == 1
            assert sum(item[1] for item in interaction_ids) == 1

            second_source_id, second_created = await repository.add_interaction(
                tenant_id=tenant_id,
                lead_id=lead_id,
                interaction_type="FORM_SUBMISSION",
                source="synthetic_website",
                source_event_id=f"website-{event_id}",
                campaign_id=campaign_id,
                content_id=content_id,
                correlation_id=correlation_id,
                occurred_at=now + timedelta(seconds=1),
                safe_payload={"synthetic": True},
            )
            assert second_created and second_source_id

            score, components = quality_score(
                {
                    "intent_quality": 25,
                    "contactability": 15,
                    "identity_confidence": 15,
                    "campaign_fit": 10,
                    "urgency": 5,
                    "source_quality": 5,
                }
            )
            assert score == 75 and sum(components.values()) == score
            positive = next_best_action(
                dnc="CLEAR",
                consent="UNKNOWN",
                intent="BUYING_INTENT",
                score=score,
                phone=True,
                email=True,
                social=True,
            )
            assert positive.action == NextAction.MANUAL_REVIEW
            assert not positive.eligible_for_contact
            assert (
                next_best_action(
                    dnc="INTERNAL_DNC",
                    consent="GRANTED",
                    intent="BUYING_INTENT",
                    score=100,
                    phone=True,
                    email=True,
                    social=True,
                ).action
                == NextAction.DO_NOT_CONTACT
            )
            assert (
                next_best_action(
                    dnc="CLEAR",
                    consent="GRANTED",
                    intent="SPAM",
                    score=100,
                    phone=True,
                    email=True,
                    social=True,
                ).action
                == NextAction.DO_NOT_CONTACT
            )
            assert (
                next_best_action(
                    dnc="CLEAR",
                    consent="GRANTED",
                    intent="SUPPORT",
                    score=50,
                    phone=False,
                    email=True,
                    social=True,
                ).action
                == NextAction.SUPPORT_HANDOFF
            )

            touch_ids = []
            for index in range(2):
                touch_id = uuid4()
                touch_ids.append(touch_id)
                await session.execute(
                    text(
                        "INSERT INTO lead_campaign_touches(id,tenant_id,lead_id,identity_id,campaign_id,content_id,network,provider,source,utm,event_type,source_event_id,occurred_at) VALUES(:id,:tenant,:lead,:person,:campaign,:content,'facebook','postly','SYNTHETIC_TEST',:utm,'CAMPAIGN_TOUCH',:source_event,:occurred)"
                    ),
                    {
                        "id": touch_id,
                        "tenant": tenant_id,
                        "lead": lead_id,
                        "person": person_id,
                        "campaign": campaign_id,
                        "content": content_id,
                        "utm": json.dumps(
                            {
                                "utm_source": "facebook",
                                "utm_medium": "social",
                                "utm_campaign": str(campaign_id),
                                "utm_content": str(content_id),
                            }
                        ),
                        "source_event": f"touch-{index}-{event_id}",
                        "occurred": now + timedelta(seconds=index),
                    },
                )
            await session.commit()

            revenue_id, revenue_created = await repository.create_revenue(
                tenant_id=tenant_id,
                lead_id=lead_id,
                event_type="PAYMENT_RECEIVED",
                amount=Decimal("1000"),
                currency="USD",
                source_system="SYNTHETIC_TEST",
                external_reference=f"synthetic-revenue-{event_id}",
                occurred_at=now + timedelta(minutes=1),
                is_synthetic=True,
            )
            duplicate_revenue_id, duplicate_created = await repository.create_revenue(
                tenant_id=tenant_id,
                lead_id=lead_id,
                event_type="PAYMENT_RECEIVED",
                amount=Decimal("1000"),
                currency="USD",
                source_system="SYNTHETIC_TEST",
                external_reference=f"synthetic-revenue-{event_id}",
                occurred_at=now + timedelta(minutes=1),
                is_synthetic=True,
            )
            assert revenue_created and not duplicate_created
            assert duplicate_revenue_id == revenue_id
            for model in (
                "FIRST_TOUCH",
                "LAST_TOUCH",
                "LINEAR",
                "POSITION_BASED",
                "TIME_DECAY",
            ):
                calculation = await repository.calculate_attribution(
                    tenant_id=tenant_id, revenue_event_id=revenue_id, model=model
                )
                assert sum(
                    item["weight"] for item in calculation["allocations"]
                ) == Decimal(1)
                assert sum(
                    item["attributed_amount"] for item in calculation["allocations"]
                ) == Decimal("1000")

            payload = {
                "tenant_id": str(tenant_id),
                "person_id": str(person_id),
                "lead_id": str(lead_id),
                "campaign_id": str(campaign_id),
                "content_id": str(content_id),
                "network": "facebook",
                "provider": "postly",
                "synthetic": True,
            }
            payload_bytes = json.dumps(payload, sort_keys=True).encode()
            integration_id = await session.scalar(
                text(
                    "INSERT INTO integration_event(idempotency_key,event_type,schema_version,original_event_id,entity_key,source_system,correlation_id,payload_json,payload_hash,state) VALUES(:idem,'social.message.received','1.0',:event,:entity,'social',:correlation,:payload,:hash,'accepted') ON CONFLICT(original_event_id) DO UPDATE SET original_event_id=excluded.original_event_id RETURNING id"
                ),
                {
                    "idem": hashlib.sha256(event_id.encode()).hexdigest(),
                    "event": event_id,
                    "entity": f"lead:{lead_id}",
                    "correlation": correlation_id,
                    "payload": json.dumps(payload),
                    "hash": hashlib.sha256(payload_bytes).hexdigest(),
                },
            )
            await session.execute(
                text(
                    "INSERT INTO integration_delivery(id,event_id,target,status,attempts,max_attempts) VALUES(:id,:event,'n8n','pending',0,5) ON CONFLICT(event_id,target) DO NOTHING"
                ),
                {"id": uuid4(), "event": integration_id},
            )
            await session.execute(
                text(
                    "INSERT INTO n8n_workflow_registry(registry_id,workflow_code,workflow_version,n8n_workflow_id,event_types,tenant_scope,enabled,timeout_seconds,retry_policy,result_contract,owner,webhook_path) VALUES(:id,'CDST_SOCIAL_EVENT_ROUTER','1',:workflow,'[\"social.message.received\"]'::jsonb,CAST(:tenants AS jsonb),true,600,CAST(:retry AS jsonb),'codestra.n8n.result.v1','synthetic-canary','/webhook/codestra-social-router-v1') ON CONFLICT(workflow_code,workflow_version) DO UPDATE SET event_types=excluded.event_types,tenant_scope=excluded.tenant_scope,enabled=true"
                ),
                {
                    "id": uuid4(),
                    "workflow": f"synthetic-router-{tenant_id}",
                    "tenants": json.dumps([str(tenant_id)]),
                    "retry": json.dumps({"max_attempts": 5}),
                },
            )
            await session.commit()
            assert await stage_pending(session) == 1
            execution_id = await session.scalar(
                text(
                    "SELECT execution_id FROM social_n8n_delivery_execution WHERE delivery_id=(SELECT id FROM integration_delivery WHERE event_id=:event AND target='n8n')"
                ),
                {"event": integration_id},
            )
            assert execution_id
            await session.execute(
                text(
                    "UPDATE n8n_runtime_execution SET status='COMPLETED' WHERE execution_id=:id"
                ),
                {"id": execution_id},
            )
            await session.commit()
            assert await reconcile_terminal(session) == 1

            stale_delivery = uuid4()
            stale_event = str(uuid4())
            stale_integration_id = await session.scalar(
                text(
                    "INSERT INTO integration_event(idempotency_key,event_type,schema_version,original_event_id,entity_key,source_system,correlation_id,payload_json,payload_hash,state) VALUES(:idem,'social.message.received','1.0',:event,:entity,'social',:correlation,'{}'::jsonb,:hash,'accepted') RETURNING id"
                ),
                {
                    "idem": stale_event,
                    "event": stale_event,
                    "entity": f"recovery:{stale_event}",
                    "correlation": correlation_id,
                    "hash": hashlib.sha256(b"{}").hexdigest(),
                },
            )
            await session.execute(
                text(
                    "INSERT INTO integration_delivery(id,event_id,target,status,attempts,lease_owner,lease_expires_at,max_attempts) VALUES(:id,:event,'n8n','leased',0,'crashed-worker',:expired,5)"
                ),
                {
                    "id": stale_delivery,
                    "event": stale_integration_id,
                    "expired": now - timedelta(minutes=1),
                },
            )
            await session.commit()
            assert await recover(session) == 1

            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM person_identities WHERE tenant_id=:tenant"
                    ),
                    {"tenant": tenant_id},
                )
                == 1
            )
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM lead_records WHERE tenant_id=:tenant"),
                    {"tenant": tenant_id},
                )
                == 1
            )
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM revenue_events WHERE tenant_id=:tenant"),
                    {"tenant": tenant_id},
                )
                == 1
            )
            assert (
                await session.scalar(
                    text("SELECT is_synthetic FROM revenue_events WHERE id=:id"),
                    {"id": revenue_id},
                )
                is True
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM attribution_allocations a JOIN attribution_calculations c ON c.id=a.calculation_id JOIN revenue_events r ON r.id=c.revenue_event_id WHERE r.tenant_id=:tenant AND r.is_synthetic=false"
                    ),
                    {"tenant": tenant_id},
                )
                == 0
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM integration_event WHERE original_event_id=:event"
                    ),
                    {"event": event_id},
                )
                == 1
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM integration_delivery WHERE event_id=:event AND target='n8n'"
                    ),
                    {"event": integration_id},
                )
                == 1
            )

            dry_run = await odoo_dry_run(
                OdooDryRunRequest(
                    tenant_id=tenant_id,
                    lead_intelligence_id=lead_id,
                    fields={
                        "campaign_id": str(campaign_id),
                        "lead_score": score,
                        "next_action": positive.action.value,
                        "source": "SOCIAL",
                    },
                ),
                permissions="social.ops.read",
            )
            assert dry_run["dry_run"] is True
            assert dry_run["write_enabled"] is False
            assert dry_run["command_dispatched"] is False
        await engine.dispose()

    asyncio.run(scenario())
