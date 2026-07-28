"""Persistent, fail-closed campaign design previews.

This module deliberately has no VICIdial, n8n, messaging, or activation client.
Approval freezes a revision; it does not provision anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


LIST_RANGES = {
    "MOY": (11000, 11999), "COD": (21000, 21999),
    "SCP": (31000, 31999), "MBL": (41000, 41999),
    "RLP": (51000, 51999), "FTP": (61000, 61999),
    "TRX": (71000, 71999), "CAL": (81000, 81999),
    "TEST": (91000, 91999),
}


class DesignConflict(RuntimeError):
    pass


class CampaignDesignInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    event_id: str = Field(min_length=8, max_length=128)
    integration_uuid: str = Field(min_length=32, max_length=64)
    odoo_campaign_id: int = Field(gt=0)
    environment: str
    business_unit: str
    purpose: str = Field(pattern=r"^[A-Z0-9]{2,16}$")
    direction: str
    owner_user_id: int = Field(gt=0)
    supervisor_user_id: int = Field(gt=0)
    correlation_id: str = Field(min_length=8, max_length=128)

    @field_validator("environment")
    @classmethod
    def environment_is_safe(cls, value: str) -> str:
        if value not in {"staging", "test"}:
            raise ValueError("campaign preview is staging/test only")
        return value

    @field_validator("business_unit")
    @classmethod
    def known_unit(cls, value: str) -> str:
        value = value.upper()
        if value not in LIST_RANGES:
            raise ValueError("unknown business unit")
        return value

    @field_validator("direction")
    @classmethod
    def known_direction(cls, value: str) -> str:
        if value not in {"inbound", "outbound", "blended"}:
            raise ValueError("unknown direction")
        return value

    def payload_hash(self) -> str:
        body = self.model_dump(exclude={"event_id", "correlation_id"})
        return hashlib.sha256(canonical(body).encode()).hexdigest()


@dataclass(frozen=True)
class StoredDesign:
    revision: int
    manifest: dict[str, Any]
    payload_hash: str
    approval_state: str


class DesignStore(Protocol):
    async def rollback(self) -> None: ...
    async def event(self, event_id: str) -> tuple[str, str] | None: ...
    async def design(self, integration_uuid: str) -> StoredDesign | None: ...
    async def create(self, request: CampaignDesignInput) -> StoredDesign: ...
    async def mark_event(self, request: CampaignDesignInput, status: str) -> None: ...
    async def fail_event(
        self, request: CampaignDesignInput, error: str, max_attempts: int
    ) -> str: ...
    async def approve(
        self, integration_uuid: str, actor: str, correlation_id: str
    ) -> StoredDesign: ...


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def build_manifest(request: CampaignDesignInput, revision: int, list_id: int) -> dict[str, Any]:
    direction = {"inbound": "IN", "outbound": "OUT", "blended": "BLD"}[
        request.direction
    ]
    campaign_code = f"{request.business_unit}-{request.purpose}-{direction}"
    prefix = f"{request.business_unit}_{request.purpose}"
    return {
        "schema_version": "campaign-provisioning.v1",
        "environment": request.environment,
        "integration_uuid": request.integration_uuid,
        "design_revision": revision,
        "business_unit": request.business_unit,
        "odoo": {
            "campaign_id": request.odoo_campaign_id,
            "campaign_code": campaign_code,
            "owner_user_id": request.owner_user_id,
            "supervisor_user_id": request.supervisor_user_id,
        },
        "vicidial": {
            "active": False,
            "default_list_id": list_id,
            "lists": [{"list_id": list_id, "code": f"{prefix}_PRIMARY_001", "active": False}],
            "user_groups": [f"{prefix}_AGENT"],
            "inbound_groups": [f"{prefix}_INBOUND", f"{prefix}_CLOSERS"],
            "scripts": [f"{prefix}_AGENT_V1"],
            "dispositions": ["DNC", "TEST"] if request.business_unit == "TEST" else ["DNC"],
        },
        "n8n": {
            "scope": f"{request.environment.upper()}-{request.business_unit}-{request.purpose}-V{revision}",
            "workflows_active": False,
        },
        "approval": {"state": "preview", "provisioning_authorized": False},
        "lifecycle": {
            "state": "approval_pending",
            "history": ["draft", "design_pending", "design_ready", "approval_pending"],
        },
        "feature_flags": {
            "vicidial_writes": False, "production_dialing": False,
            "n8n_production": False, "email": False, "sms": False,
            "ai_actions": False,
        },
    }


class CampaignDesignService:
    def __init__(self, store: DesignStore):
        self.store = store

    async def consume(self, request: CampaignDesignInput, *, max_attempts: int = 3) -> dict[str, Any]:
        prior_event = await self.store.event(request.event_id)
        if prior_event:
            prior_hash, status = prior_event
            if prior_hash != request.payload_hash():
                raise DesignConflict("event replay payload conflict")
            existing = await self.store.design(request.integration_uuid)
            if status == "completed" and existing:
                return existing.manifest | {"idempotent_replay": True}
        try:
            existing = await self.store.design(request.integration_uuid)
            if existing:
                if existing.payload_hash != request.payload_hash():
                    raise DesignConflict("integration UUID payload conflict")
                await self.store.mark_event(request, "completed")
                return existing.manifest | {"idempotent_replay": True}
            created = await self.store.create(request)
            await self.store.mark_event(request, "completed")
            return created.manifest | {"idempotent_replay": False}
        except DesignConflict:
            await self.store.rollback()
            await self.store.fail_event(request, "design conflict", 1)
            raise
        except Exception as exc:
            await self.store.rollback()
            await self.store.fail_event(request, type(exc).__name__, max_attempts)
            raise

    async def approve(
        self, integration_uuid: str, actor: str, correlation_id: str
    ) -> dict[str, Any]:
        stored = await self.store.approve(integration_uuid, actor, correlation_id)
        result = dict(stored.manifest)
        result["approval"] = {
            "state": "approved", "actor": actor,
            "provisioning_authorized": False,
        }
        result["lifecycle"] = {
            "state": "approved",
            "history": [
                "draft", "design_pending", "design_ready",
                "approval_pending", "approved",
            ],
            "next_state": "provisioning_pending",
            "adapter_delivery_enabled": False,
        }
        return result


class PostgresDesignStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def rollback(self) -> None:
        await self.db.rollback()

    async def event(self, event_id: str) -> tuple[str, str] | None:
        row = (await self.db.execute(text(
            "SELECT payload_hash,status FROM campaign_design_event WHERE event_id=:id"
        ), {"id": event_id})).mappings().one_or_none()
        return (row["payload_hash"], row["status"]) if row else None

    async def design(self, integration_uuid: str) -> StoredDesign | None:
        row = (await self.db.execute(text(
            "SELECT revision,manifest,payload_hash,approval_state "
            "FROM campaign_design_revision WHERE integration_uuid=:uuid "
            "ORDER BY revision DESC LIMIT 1"
        ), {"uuid": integration_uuid})).mappings().one_or_none()
        return StoredDesign(**dict(row)) if row else None

    async def create(self, request: CampaignDesignInput) -> StoredDesign:
        low, high = LIST_RANGES[request.business_unit]
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:scope))"),
            {"scope": f"campaign-list:{request.environment}:{request.business_unit}"},
        )
        list_id = (await self.db.execute(text(
            "SELECT candidate FROM generate_series("
            "CAST(:low AS integer),CAST(:high AS integer)) candidate "
            "WHERE NOT EXISTS (SELECT 1 FROM campaign_list_reservation "
            "WHERE environment=:environment AND list_id=candidate) "
            "ORDER BY candidate LIMIT 1"
        ), {"low": low, "high": high, "environment": request.environment})).scalar_one_or_none()
        if list_id is None:
            raise DesignConflict("list range exhausted")
        manifest = build_manifest(request, 1, int(list_id))
        await self.db.execute(text(
            "INSERT INTO campaign_list_reservation"
            "(environment,business_unit,list_id,integration_uuid,revision) "
            "VALUES(:environment,:unit,:list_id,:uuid,1)"
        ), {"environment": request.environment, "unit": request.business_unit,
            "list_id": list_id, "uuid": request.integration_uuid})
        await self.db.execute(text(
            "INSERT INTO campaign_design_revision"
            "(integration_uuid,revision,payload_hash,manifest,approval_state) "
            "VALUES(:uuid,1,:hash,CAST(:manifest AS jsonb),'preview')"
        ), {"uuid": request.integration_uuid, "hash": request.payload_hash(),
            "manifest": canonical(manifest)})
        await self.db.commit()
        return StoredDesign(1, manifest, request.payload_hash(), "preview")

    async def mark_event(self, request: CampaignDesignInput, status: str) -> None:
        await self.db.execute(text(
            "INSERT INTO campaign_design_event"
            "(event_id,integration_uuid,payload_hash,status,attempts,correlation_id) "
            "VALUES(:event,:uuid,:hash,:status,0,:correlation) "
            "ON CONFLICT(event_id) DO UPDATE SET status=excluded.status"
        ), {"event": request.event_id, "uuid": request.integration_uuid,
            "hash": request.payload_hash(), "status": status,
            "correlation": request.correlation_id})
        await self.db.execute(text(
            "INSERT INTO audit_event"
            "(id,action,subject,correlation_id,decision,redacted_payload) "
            "VALUES(:id,'campaign.design.consumed',:subject,:correlation,:decision,"
            "CAST(:payload AS jsonb))"
        ), {"id": uuid4(), "subject": request.integration_uuid,
            "correlation": request.correlation_id, "decision": status,
            "payload": canonical({
                "event_id_hash": hashlib.sha256(
                    request.event_id.encode()
                ).hexdigest(),
                "business_unit": request.business_unit,
            })})
        await self.db.commit()

    async def fail_event(self, request: CampaignDesignInput, error: str, max_attempts: int) -> str:
        row = (await self.db.execute(text(
            "INSERT INTO campaign_design_event"
            "(event_id,integration_uuid,payload_hash,status,attempts,last_error,correlation_id) "
            "VALUES(:event,:uuid,:hash,'retry',1,:error,:correlation) "
            "ON CONFLICT(event_id) DO UPDATE SET attempts=campaign_design_event.attempts+1,"
            "last_error=excluded.last_error RETURNING attempts"
        ), {"event": request.event_id, "uuid": request.integration_uuid,
            "hash": request.payload_hash(), "error": error[:128],
            "correlation": request.correlation_id})).scalar_one()
        status = "dead_letter" if row >= max_attempts else "retry"
        next_attempt_at = (
            None
            if status == "dead_letter"
            else datetime.now(timezone.utc)
            + timedelta(seconds=min(300, 2 ** max(0, row - 1)))
        )
        await self.db.execute(text(
            "UPDATE campaign_design_event SET status=:status,"
            "next_attempt_at=:next_attempt_at WHERE event_id=:event"
        ), {"status": status, "next_attempt_at": next_attempt_at,
            "event": request.event_id})
        await self.db.commit()
        return status

    async def approve(
        self, integration_uuid: str, actor: str, correlation_id: str
    ) -> StoredDesign:
        row = (await self.db.execute(text(
            "UPDATE campaign_design_revision SET approval_state='approved',"
            "approved_by=:actor,approved_at=now() "
            "WHERE integration_uuid=:uuid AND revision=("
            "SELECT max(revision) FROM campaign_design_revision "
            "WHERE integration_uuid=:uuid) "
            "AND approval_state IN ('preview','approved') "
            "RETURNING revision,manifest,payload_hash,approval_state"
        ), {"uuid": integration_uuid, "actor": actor})).mappings().one_or_none()
        if not row:
            raise DesignConflict("design revision missing or immutable")
        await self.db.execute(text(
            "INSERT INTO audit_event"
            "(id,action,subject,correlation_id,decision,redacted_payload) "
            "VALUES(:id,'campaign.design.approved',:subject,:correlation,"
            "'approved',CAST(:payload AS jsonb))"
        ), {"id": uuid4(), "subject": integration_uuid,
            "correlation": correlation_id,
            "payload": canonical({"actor_hash": hashlib.sha256(
                actor.encode()
            ).hexdigest()})})
        await self.db.commit()
        return StoredDesign(**dict(row))
