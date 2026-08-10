from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.domain import CampaignState, require_transition


class PlatformRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_campaign(
        self,
        *,
        tenant_id: UUID,
        name: str,
        objective: str,
        correlation_id: str,
        actor: str,
    ) -> dict[str, Any]:
        campaign_id = uuid4()
        now = datetime.now(timezone.utc)
        await self.session.execute(
            text("""INSERT INTO platform_campaigns
            (id,tenant_id,name,objective,state,created_at,updated_at)
            VALUES (:id,:tenant,:name,:objective,'DRAFT',:now,:now)"""),
            {
                "id": campaign_id,
                "tenant": tenant_id,
                "name": name,
                "objective": objective,
                "now": now,
            },
        )
        await self._transition_audit(
            campaign_id, None, CampaignState.DRAFT, "created", correlation_id, actor
        )
        await self.session.commit()
        return {
            "id": campaign_id,
            "tenant_id": tenant_id,
            "name": name,
            "objective": objective,
            "state": CampaignState.DRAFT,
            "created_at": now,
            "updated_at": now,
        }

    async def get_campaign(
        self, campaign_id: UUID, tenant_id: UUID
    ) -> dict[str, Any] | None:
        row = (
            (
                await self.session.execute(
                    text("""SELECT id,tenant_id,name,objective,state,created_at,updated_at
            FROM platform_campaigns WHERE id=:id AND tenant_id=:tenant"""),
                    {"id": campaign_id, "tenant": tenant_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row else None

    async def transition(
        self,
        *,
        campaign_id: UUID,
        tenant_id: UUID,
        target: CampaignState,
        reason: str,
        correlation_id: str,
        actor: str,
    ) -> dict[str, Any] | None:
        row = (
            (
                await self.session.execute(
                    text(
                        "SELECT state FROM platform_campaigns WHERE id=:id AND tenant_id=:tenant FOR UPDATE"
                    ),
                    {"id": campaign_id, "tenant": tenant_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if not row:
            await self.session.rollback()
            return None
        old = CampaignState(row["state"])
        require_transition(old, target)
        now = datetime.now(timezone.utc)
        await self.session.execute(
            text(
                "UPDATE platform_campaigns SET state=:state,updated_at=:now WHERE id=:id"
            ),
            {"state": target.value, "now": now, "id": campaign_id},
        )
        await self._transition_audit(
            campaign_id, old, target, reason, correlation_id, actor
        )
        await self.session.commit()
        return {"id": campaign_id, "old_state": old, "state": target, "updated_at": now}

    async def add_content(
        self,
        *,
        campaign_id: UUID,
        tenant_id: UUID,
        network: str,
        language: str,
        text_value: str,
        ai_generated: bool,
        ai_model_reference: str | None,
        risk_status: str,
        correlation_id: str,
        actor: str,
    ) -> dict[str, Any] | None:
        exists = (
            await self.session.execute(
                text(
                    "SELECT 1 FROM platform_campaigns WHERE id=:id AND tenant_id=:tenant"
                ),
                {"id": campaign_id, "tenant": tenant_id},
            )
        ).scalar_one_or_none()
        if not exists:
            return None
        content_id = uuid4()
        version = (
            await self.session.execute(
                text(
                    "SELECT COALESCE(MAX(version),0)+1 FROM campaign_content_versions WHERE campaign_id=:id AND network=:network AND language=:language"
                ),
                {"id": campaign_id, "network": network, "language": language},
            )
        ).scalar_one()
        await self.session.execute(
            text("""INSERT INTO campaign_content_versions
          (id,campaign_id,version,language,network,text_content,ai_generated,ai_model_reference,risk_status,approval_status,created_by,correlation_id)
          VALUES (:id,:campaign,:version,:language,:network,:content,:ai,:model,:risk,'PENDING',:actor,:correlation)"""),
            {
                "id": content_id,
                "campaign": campaign_id,
                "version": version,
                "language": language,
                "network": network,
                "content": text_value,
                "ai": ai_generated,
                "model": ai_model_reference,
                "risk": risk_status,
                "actor": actor,
                "correlation": correlation_id,
            },
        )
        await self.session.commit()
        return {
            "id": content_id,
            "campaign_id": campaign_id,
            "version": version,
            "language": language,
            "network": network,
            "risk_status": risk_status,
            "approval_status": "PENDING",
        }

    async def approve_content(
        self,
        *,
        content_id: UUID,
        tenant_id: UUID,
        version: int,
        decision: str,
        reason: str,
        actor: str,
        correlation_id: str,
    ) -> dict[str, Any] | None:
        row = (
            (
                await self.session.execute(
                    text("""SELECT c.id,c.version,c.risk_status,c.approval_status
          FROM campaign_content_versions c JOIN platform_campaigns p ON p.id=c.campaign_id
          WHERE c.id=:id AND c.version=:version AND p.tenant_id=:tenant FOR UPDATE"""),
                    {"id": content_id, "version": version, "tenant": tenant_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if not row:
            await self.session.rollback()
            return None
        if decision == "APPROVED" and row["risk_status"] == "BLOCKED":
            raise ValueError("SOCIAL_CONTENT_RISK_BLOCKED")
        approval_id = uuid4()
        await self.session.execute(
            text("""INSERT INTO campaign_approvals
          (id,content_id,content_version,actor,decision,reason,correlation_id)
          VALUES (:id,:content,:version,:actor,:decision,:reason,:correlation)"""),
            {
                "id": approval_id,
                "content": content_id,
                "version": version,
                "actor": actor,
                "decision": decision,
                "reason": reason,
                "correlation": correlation_id,
            },
        )
        await self.session.execute(
            text(
                "UPDATE campaign_content_versions SET approval_status=:decision,approved_by=:actor,approved_at=now() WHERE id=:id"
            ),
            {"decision": decision, "actor": actor, "id": content_id},
        )
        await self.session.commit()
        return {
            "approval_id": approval_id,
            "content_id": content_id,
            "version": version,
            "decision": decision,
        }

    async def _transition_audit(
        self,
        campaign_id: UUID,
        old: CampaignState | None,
        new: CampaignState,
        reason: str,
        correlation_id: str,
        actor: str,
    ) -> None:
        await self.session.execute(
            text("""INSERT INTO campaign_state_transitions
          (id,campaign_id,old_state,new_state,reason,actor,correlation_id)
          VALUES (:id,:campaign,:old,:new,:reason,:actor,:correlation)"""),
            {
                "id": uuid4(),
                "campaign": campaign_id,
                "old": old.value if old else None,
                "new": new.value,
                "reason": reason,
                "actor": actor,
                "correlation": correlation_id,
            },
        )

    async def list_dead_letters(
        self, tenant_id: UUID, limit: int
    ) -> list[dict[str, Any]]:
        rows = (
            (
                await self.session.execute(
                    text("""SELECT id,job_type,provider,attempt_count,last_error_code,last_error_summary,
          correlation_id,failed_at FROM social_publish_jobs WHERE tenant_id=:tenant AND state='failed'
          ORDER BY failed_at DESC NULLS LAST,id LIMIT :limit"""),
                    {"tenant": tenant_id, "limit": limit},
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    async def store_lead_intelligence(
        self,
        *,
        tenant_id: UUID,
        campaign_id: UUID | None,
        source_event_id: str,
        category: str,
        quality_score: int,
        factors: dict[str, int],
        identity_hash: str | None,
        consent_status: str,
        dnc_status: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        result_id = uuid4()
        row = (
            (
                await self.session.execute(
                    text("""INSERT INTO lead_intelligence_results
                    (id,tenant_id,campaign_id,source_event_id,category,quality_score,
                    factor_summary,identity_hash,consent_status,dnc_status,correlation_id)
                    VALUES (:id,:tenant,:campaign,:event,:category,:score,:factors,:identity,:consent,:dnc,:correlation)
                    ON CONFLICT (tenant_id,source_event_id) DO NOTHING
                    RETURNING id"""),
                    {
                        "id": result_id,
                        "tenant": tenant_id,
                        "campaign": campaign_id,
                        "event": source_event_id,
                        "category": category,
                        "score": quality_score,
                        "factors": json.dumps(factors, sort_keys=True),
                        "identity": identity_hash,
                        "consent": consent_status,
                        "dnc": dnc_status,
                        "correlation": correlation_id,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        duplicate = row is None
        if duplicate:
            result_id = (
                await self.session.execute(
                    text(
                        "SELECT id FROM lead_intelligence_results WHERE tenant_id=:tenant AND source_event_id=:event"
                    ),
                    {"tenant": tenant_id, "event": source_event_id},
                )
            ).scalar_one()
        await self.session.commit()
        return {
            "id": result_id,
            "category": category,
            "quality_score": quality_score,
            "factors": factors,
            "duplicate": duplicate,
            "eligible_for_outreach": False,
            "odoo_projection": "DRY_RUN_ONLY",
        }

    async def register_media(
        self,
        *,
        tenant_id: UUID,
        content_type: str,
        size_bytes: int,
        checksum: str,
        storage_backend: str,
        location_reference: str,
        expires_at: datetime | None,
    ) -> dict[str, Any]:
        asset_id = uuid4()
        row = (
            (
                await self.session.execute(
                    text("""INSERT INTO platform_media_assets
                    (id,tenant_id,content_type,size_bytes,checksum,storage_backend,location_reference,status,expires_at)
                    VALUES (:id,:tenant,:type,:size,:checksum,:backend,:location,'REGISTERED',:expires)
                    ON CONFLICT (tenant_id,checksum) DO UPDATE SET checksum=EXCLUDED.checksum
                    RETURNING id,status"""),
                    {
                        "id": asset_id,
                        "tenant": tenant_id,
                        "type": content_type,
                        "size": size_bytes,
                        "checksum": checksum,
                        "backend": storage_backend,
                        "location": location_reference,
                        "expires": expires_at,
                    },
                )
            )
            .mappings()
            .one()
        )
        await self.session.commit()
        return {
            "asset_id": row["id"],
            "status": row["status"],
            "content_type": content_type,
            "size_bytes": size_bytes,
            "checksum": checksum,
            "storage_backend": storage_backend,
        }
