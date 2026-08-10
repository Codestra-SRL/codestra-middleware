from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.domain import attribution_weights, stable_hash


class LeadRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def resolve_person(
        self,
        *,
        tenant_id: UUID,
        display_name: str | None,
        email: str | None,
        phone: str | None,
        social: tuple[str, str, str] | None,
        correlation_id: str,
    ) -> dict[str, Any]:
        keys = [("EMAIL", stable_hash(email))] if email else []
        keys += [("PHONE", stable_hash(phone))] if phone else []
        if social:
            keys += [("SOCIAL", stable_hash(*social))]
        lock_key = stable_hash(str(tenant_id), *(value for _, value in keys))
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": lock_key},
        )
        matches: set[UUID] = set()
        for kind, hashed in keys:
            if kind == "SOCIAL":
                if social is None:
                    raise ValueError("SOCIAL_IDENTITY_INVALID")
                row = (
                    await self.session.execute(
                        text(
                            "SELECT person_id FROM social_identities WHERE tenant_id=:tenant AND provider=:provider AND network=:network AND provider_profile_id=:profile"
                        ),
                        {
                            "tenant": tenant_id,
                            "provider": social[0],
                            "network": social[1],
                            "profile": social[2],
                        },
                    )
                ).scalar_one_or_none()
            else:
                row = (
                    await self.session.execute(
                        text(
                            "SELECT person_id FROM contact_points WHERE tenant_id=:tenant AND type=:kind AND normalized_hash=:hash"
                        ),
                        {"tenant": tenant_id, "kind": kind, "hash": hashed},
                    )
                ).scalar_one_or_none()
            if row:
                matches.add(row)
        if len(matches) > 1:
            attempt_id = uuid4()
            await self.session.execute(
                text(
                    "INSERT INTO identity_resolution_attempts(id,tenant_id,request_hash,confidence,score,signal_summary,conflict,correlation_id) VALUES(:id,:tenant,:hash,'UNKNOWN',0,:signals,true,:correlation)"
                ),
                {
                    "id": attempt_id,
                    "tenant": tenant_id,
                    "hash": lock_key,
                    "signals": json.dumps({"conflicting_identity_count": len(matches)}),
                    "correlation": correlation_id,
                },
            )
            await self.session.commit()
            return {
                "status": "CONFLICT",
                "confidence": "UNKNOWN",
                "review_required": True,
                "resolution_attempt_id": attempt_id,
            }
        created = not matches
        person_id = next(iter(matches), uuid4())
        if created:
            await self.session.execute(
                text(
                    "INSERT INTO person_identities(id,tenant_id,display_name) VALUES(:id,:tenant,:name)"
                ),
                {"id": person_id, "tenant": tenant_id, "name": display_name},
            )
        for kind, hashed in keys:
            if kind != "SOCIAL":
                masked = "***" + (
                    email[-8:]
                    if kind == "EMAIL" and email
                    else (phone[-4:] if phone else "")
                )
                await self.session.execute(
                    text(
                        "INSERT INTO contact_points(id,tenant_id,person_id,type,normalized_hash,display_masked,normalization_status,source) VALUES(:id,:tenant,:person,:kind,:hash,:masked,'NORMALIZED','INGESTION') ON CONFLICT (tenant_id,type,normalized_hash) DO UPDATE SET last_seen_at=now()"
                    ),
                    {
                        "id": uuid4(),
                        "tenant": tenant_id,
                        "person": person_id,
                        "kind": kind,
                        "hash": hashed,
                        "masked": masked,
                    },
                )
        if social:
            await self.session.execute(
                text(
                    "INSERT INTO social_identities(id,tenant_id,provider,network,provider_profile_id,person_id) VALUES(:id,:tenant,:provider,:network,:profile,:person) ON CONFLICT (tenant_id,provider,network,provider_profile_id) DO UPDATE SET last_seen_at=now()"
                ),
                {
                    "id": uuid4(),
                    "tenant": tenant_id,
                    "provider": social[0],
                    "network": social[1],
                    "profile": social[2],
                    "person": person_id,
                },
            )
        attempt_id = uuid4()
        await self.session.execute(
            text(
                "INSERT INTO identity_resolution_attempts(id,tenant_id,request_hash,result_identity_id,confidence,score,signal_summary,correlation_id) VALUES(:id,:tenant,:hash,:person,'EXACT',100,:signals,:correlation)"
            ),
            {
                "id": attempt_id,
                "tenant": tenant_id,
                "hash": lock_key,
                "person": person_id,
                "signals": json.dumps(
                    {"keys": [kind for kind, _ in keys], "created": created}
                ),
                "correlation": correlation_id,
            },
        )
        await self.session.commit()
        return {
            "person_id": person_id,
            "created": created,
            "confidence": "EXACT",
            "auto_linked": True,
            "resolution_attempt_id": attempt_id,
        }

    async def get_person(
        self, tenant_id: UUID, person_id: UUID
    ) -> dict[str, Any] | None:
        row = (
            (
                await self.session.execute(
                    text(
                        "SELECT id,tenant_id,display_name,first_name,last_name,preferred_language,country,timezone,status,merged_into_id,created_at,updated_at FROM person_identities WHERE id=:id AND tenant_id=:tenant"
                    ),
                    {"id": person_id, "tenant": tenant_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row else None

    async def resolve_company(
        self,
        *,
        tenant_id: UUID,
        legal_name: str | None,
        display_name: str | None,
        domain: str | None,
        registration_number: str | None,
        country: str | None,
        correlation_id: str,
    ) -> dict[str, Any]:
        key = stable_hash(str(tenant_id), domain, registration_number)
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": key}
        )
        row = (
            await self.session.execute(
                text(
                    "SELECT id FROM company_identities WHERE tenant_id=:tenant AND merged_into_id IS NULL AND ((CAST(:domain AS varchar) IS NOT NULL AND domain=CAST(:domain AS varchar)) OR (CAST(:registration AS varchar) IS NOT NULL AND registration_number=CAST(:registration AS varchar))) FOR UPDATE"
                ),
                {
                    "tenant": tenant_id,
                    "domain": domain,
                    "registration": registration_number,
                },
            )
        ).scalar_one_or_none()
        created = row is None
        company_id = row or uuid4()
        if created:
            await self.session.execute(
                text(
                    "INSERT INTO company_identities(id,tenant_id,legal_name,display_name,domain,country,registration_number,provenance) VALUES(:id,:tenant,:legal,:display,:domain,:country,:registration,:provenance)"
                ),
                {
                    "id": company_id,
                    "tenant": tenant_id,
                    "legal": legal_name,
                    "display": display_name,
                    "domain": domain,
                    "country": country,
                    "registration": registration_number,
                    "provenance": json.dumps({"source": "INGESTION"}),
                },
            )
        attempt_id = uuid4()
        await self.session.execute(
            text(
                "INSERT INTO identity_resolution_attempts(id,tenant_id,request_hash,result_identity_id,confidence,score,signal_summary,correlation_id) VALUES(:id,:tenant,:hash,:company,'EXACT',100,:signals,:correlation)"
            ),
            {
                "id": attempt_id,
                "tenant": tenant_id,
                "hash": key,
                "company": company_id,
                "signals": json.dumps(
                    {
                        "domain": bool(domain),
                        "registration": bool(registration_number),
                        "created": created,
                    }
                ),
                "correlation": correlation_id,
            },
        )
        await self.session.commit()
        return {
            "company_id": company_id,
            "created": created,
            "confidence": "EXACT",
            "auto_linked": True,
            "resolution_attempt_id": attempt_id,
        }

    async def get_company(
        self, tenant_id: UUID, company_id: UUID
    ) -> dict[str, Any] | None:
        row = (
            (
                await self.session.execute(
                    text(
                        "SELECT id,tenant_id,legal_name,display_name,domain,country,industry,registration_number,status,merged_into_id,provenance,created_at,updated_at FROM company_identities WHERE id=:id AND tenant_id=:tenant"
                    ),
                    {"id": company_id, "tenant": tenant_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row else None

    async def upsert_lead(
        self,
        *,
        tenant_id: UUID,
        person_id: UUID | None,
        company_id: UUID | None,
        campaign_id: UUID | None,
        source: str,
        consent: str,
        dnc: str,
    ) -> tuple[UUID, bool]:
        key = stable_hash(
            str(tenant_id), str(person_id), str(company_id), str(campaign_id)
        )
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"), {"key": key}
        )
        lead_id = (
            await self.session.execute(
                text(
                    "SELECT id FROM lead_records WHERE tenant_id=:tenant AND person_id IS NOT DISTINCT FROM :person AND company_id IS NOT DISTINCT FROM :company AND campaign_id IS NOT DISTINCT FROM :campaign AND status NOT IN ('LOST','ARCHIVED') LIMIT 1 FOR UPDATE"
                ),
                {
                    "tenant": tenant_id,
                    "person": person_id,
                    "company": company_id,
                    "campaign": campaign_id,
                },
            )
        ).scalar_one_or_none()
        created = lead_id is None
        lead_id = lead_id or uuid4()
        if created:
            await self.session.execute(
                text(
                    "INSERT INTO lead_records(id,tenant_id,person_id,company_id,source,campaign_id,consent_status,dnc_status) VALUES(:id,:tenant,:person,:company,:source,:campaign,:consent,:dnc)"
                ),
                {
                    "id": lead_id,
                    "tenant": tenant_id,
                    "person": person_id,
                    "company": company_id,
                    "source": source,
                    "campaign": campaign_id,
                    "consent": consent,
                    "dnc": dnc,
                },
            )
        await self.session.commit()
        return lead_id, created

    async def add_interaction(
        self,
        *,
        tenant_id: UUID,
        lead_id: UUID,
        interaction_type: str,
        source: str,
        source_event_id: str,
        campaign_id: UUID | None,
        content_id: UUID | None,
        correlation_id: str,
        occurred_at: datetime,
        safe_payload: dict[str, Any],
    ) -> tuple[UUID, bool]:
        interaction_id = uuid4()
        row = (
            await self.session.execute(
                text(
                    "INSERT INTO lead_interactions(id,tenant_id,lead_id,interaction_type,source,source_event_id,campaign_id,content_id,correlation_id,safe_payload,occurred_at) VALUES(:id,:tenant,:lead,:type,:source,:event,:campaign,:content,:correlation,:payload,:occurred) ON CONFLICT (tenant_id,source,source_event_id) DO NOTHING RETURNING id"
                ),
                {
                    "id": interaction_id,
                    "tenant": tenant_id,
                    "lead": lead_id,
                    "type": interaction_type,
                    "source": source,
                    "event": source_event_id,
                    "campaign": campaign_id,
                    "content": content_id,
                    "correlation": correlation_id,
                    "payload": json.dumps(safe_payload),
                    "occurred": occurred_at,
                },
            )
        ).scalar_one_or_none()
        if row is None:
            interaction_id = (
                await self.session.execute(
                    text(
                        "SELECT id FROM lead_interactions WHERE tenant_id=:tenant AND source=:source AND source_event_id=:event"
                    ),
                    {"tenant": tenant_id, "source": source, "event": source_event_id},
                )
            ).scalar_one()
        await self.session.commit()
        return interaction_id, row is not None

    async def merge_person(
        self,
        *,
        tenant_id: UUID,
        source: UUID,
        target: UUID,
        actor: str,
        reason: str,
        correlation_id: str,
    ) -> UUID:
        if source == target:
            raise ValueError("IDENTITY_MERGE_SELF")
        rows = (
            (
                await self.session.execute(
                    text(
                        "SELECT id,merged_into_id FROM person_identities WHERE tenant_id=:tenant AND id IN (:source,:target) FOR UPDATE"
                    ),
                    {"tenant": tenant_id, "source": source, "target": target},
                )
            )
            .mappings()
            .all()
        )
        if len(rows) != 2 or any(row["merged_into_id"] for row in rows):
            raise ValueError("IDENTITY_MERGE_INVALID")
        decision = uuid4()
        await self.session.execute(
            text(
                "UPDATE person_identities SET merged_into_id=:target,status='MERGED',updated_at=now() WHERE id=:source"
            ),
            {"source": source, "target": target},
        )
        await self.session.execute(
            text(
                "INSERT INTO identity_merge_decisions(id,tenant_id,entity_type,source_id,target_id,actor,action,confidence,evidence,reason,correlation_id) VALUES(:id,:tenant,'PERSON',:source,:target,:actor,'MERGE','EXACT','{}'::jsonb,:reason,:correlation)"
            ),
            {
                "id": decision,
                "tenant": tenant_id,
                "source": source,
                "target": target,
                "actor": actor,
                "reason": reason,
                "correlation": correlation_id,
            },
        )
        await self.session.commit()
        return decision

    async def unmerge_person(
        self,
        *,
        tenant_id: UUID,
        source: UUID,
        actor: str,
        reason: str,
        correlation_id: str,
    ) -> UUID:
        target = (
            await self.session.execute(
                text(
                    "SELECT merged_into_id FROM person_identities WHERE id=:source AND tenant_id=:tenant FOR UPDATE"
                ),
                {"source": source, "tenant": tenant_id},
            )
        ).scalar_one_or_none()
        if not target:
            raise ValueError("IDENTITY_NOT_MERGED")
        decision = uuid4()
        await self.session.execute(
            text(
                "UPDATE person_identities SET merged_into_id=NULL,status='ACTIVE',updated_at=now() WHERE id=:source"
            ),
            {"source": source},
        )
        await self.session.execute(
            text(
                "INSERT INTO identity_merge_decisions(id,tenant_id,entity_type,source_id,target_id,actor,action,confidence,evidence,reason,correlation_id) VALUES(:id,:tenant,'PERSON',:source,:target,:actor,'UNMERGE','EXACT','{}'::jsonb,:reason,:correlation)"
            ),
            {
                "id": decision,
                "tenant": tenant_id,
                "source": source,
                "target": target,
                "actor": actor,
                "reason": reason,
                "correlation": correlation_id,
            },
        )
        await self.session.commit()
        return decision

    async def create_revenue(
        self,
        *,
        tenant_id: UUID,
        lead_id: UUID,
        event_type: str,
        amount: Decimal | None,
        currency: str | None,
        source_system: str,
        external_reference: str,
        occurred_at: datetime,
        is_synthetic: bool = False,
    ) -> tuple[UUID, bool]:
        event_id = uuid4()
        row = (
            await self.session.execute(
                text(
                    "INSERT INTO revenue_events(id,tenant_id,lead_id,amount,currency,type,occurred_at,source_system,external_reference_hash,confidence,is_synthetic) VALUES(:id,:tenant,:lead,:amount,:currency,:type,:occurred,:source,:hash,'EXACT',:synthetic) ON CONFLICT (tenant_id,source_system,external_reference_hash) DO NOTHING RETURNING id"
                ),
                {
                    "id": event_id,
                    "tenant": tenant_id,
                    "lead": lead_id,
                    "amount": amount,
                    "currency": currency,
                    "type": event_type,
                    "occurred": occurred_at,
                    "source": source_system,
                    "hash": stable_hash(external_reference),
                    "synthetic": is_synthetic,
                },
            )
        ).scalar_one_or_none()
        if row is None:
            event_id = (
                await self.session.execute(
                    text(
                        "SELECT id FROM revenue_events WHERE tenant_id=:tenant AND source_system=:source AND external_reference_hash=:hash"
                    ),
                    {
                        "tenant": tenant_id,
                        "source": source_system,
                        "hash": stable_hash(external_reference),
                    },
                )
            ).scalar_one()
        await self.session.commit()
        return event_id, row is not None

    async def calculate_attribution(
        self, *, tenant_id: UUID, revenue_event_id: UUID, model: str
    ) -> dict[str, Any]:
        event = (
            (
                await self.session.execute(
                    text(
                        "SELECT lead_id,amount,currency,occurred_at FROM revenue_events WHERE id=:id AND tenant_id=:tenant"
                    ),
                    {"id": revenue_event_id, "tenant": tenant_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if not event:
            raise ValueError("REVENUE_EVENT_NOT_FOUND")
        touches = (
            (
                await self.session.execute(
                    text(
                        "SELECT id,campaign_id,content_id,occurred_at FROM lead_campaign_touches WHERE tenant_id=:tenant AND lead_id=:lead AND occurred_at<=:occurred ORDER BY occurred_at,id"
                    ),
                    {
                        "tenant": tenant_id,
                        "lead": event["lead_id"],
                        "occurred": event["occurred_at"],
                    },
                )
            )
            .mappings()
            .all()
        )
        weights = attribution_weights(
            model, [row["occurred_at"] for row in touches], event["occurred_at"]
        )
        version = (
            await self.session.execute(
                text(
                    "SELECT COALESCE(MAX(version),0)+1 FROM attribution_calculations WHERE revenue_event_id=:id AND model=:model"
                ),
                {"id": revenue_event_id, "model": model},
            )
        ).scalar_one()
        calculation_id = uuid4()
        await self.session.execute(
            text(
                "UPDATE attribution_calculations SET superseded=true WHERE revenue_event_id=:id AND model=:model"
            ),
            {"id": revenue_event_id, "model": model},
        )
        await self.session.execute(
            text(
                "INSERT INTO attribution_calculations(id,revenue_event_id,version,model,settings) VALUES(:id,:event,:version,:model,:settings)"
            ),
            {
                "id": calculation_id,
                "event": revenue_event_id,
                "version": version,
                "model": model,
                "settings": json.dumps({"position": [0.4, 0.4], "half_life_days": 7}),
            },
        )
        allocations = []
        for touch, weight in zip(touches, weights, strict=True):
            amount = (
                Decimal(event["amount"]) * weight
                if event["amount"] is not None
                else None
            )
            allocation_id = uuid4()
            await self.session.execute(
                text(
                    "INSERT INTO attribution_allocations(id,calculation_id,touch_id,campaign_id,content_id,weight,attributed_amount,currency) VALUES(:id,:calculation,:touch,:campaign,:content,:weight,:amount,:currency)"
                ),
                {
                    "id": allocation_id,
                    "calculation": calculation_id,
                    "touch": touch["id"],
                    "campaign": touch["campaign_id"],
                    "content": touch["content_id"],
                    "weight": weight,
                    "amount": amount,
                    "currency": event["currency"],
                },
            )
            allocations.append(
                {
                    "touch_id": touch["id"],
                    "campaign_id": touch["campaign_id"],
                    "weight": weight,
                    "attributed_amount": amount,
                    "currency": event["currency"],
                }
            )
        await self.session.commit()
        return {
            "calculation_id": calculation_id,
            "version": version,
            "model": model,
            "allocations": allocations,
        }
