"""Concurrency-safe callback scheduler and recovery primitives."""

from __future__ import annotations
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import CallbackDelivery, CallbackEvent, CallbackRecord


async def claim_due(
    db: AsyncSession,
    worker_id: str,
    limit: int = 100,
    now: datetime | None = None,
    tenant_id: str | None = None,
    campaign_id: str | None = None,
) -> list[CallbackRecord]:
    now = now or datetime.now(UTC)
    query = select(CallbackRecord).where(
        CallbackRecord.state.in_(
            ["SCHEDULED", "REMINDER_PENDING", "READY", "SNOOZED", "RESCHEDULED"]
        ),
        CallbackRecord.scheduled_at <= now,
    )
    if tenant_id is not None:
        query = query.where(CallbackRecord.tenant_id == tenant_id)
    if campaign_id is not None:
        query = query.where(CallbackRecord.campaign_id == campaign_id)
    rows = (
        await db.scalars(
            query.order_by(CallbackRecord.scheduled_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
    ).all()
    for row in rows:
        old = row.state
        row.state = row.desired_state = row.actual_state = "DUE"
        row.version += 1
        row.sync_state = "PENDING"
        db.add(
            CallbackEvent(
                id=uuid4(),
                callback_id=row.id,
                tenant_id=row.tenant_id,
                campaign_id=row.campaign_id,
                event_type="callback.due",
                version=row.version,
                idempotency_key=f"callback:{row.id}:v{row.version}:due",
                correlation_id=row.correlation_id,
                actor_id=worker_id,
                payload_json={"previous_state": old},
            )
        )
        if row.reminder_popup_enabled:
            db.add(
                CallbackDelivery(
                    id=uuid4(),
                    callback_id=row.id,
                    callback_version=row.version,
                    channel="POPUP",
                    stage="DUE",
                    idempotency_key=f"callback:{row.id}:v{row.version}:popup:due",
                    status="QUEUED",
                    next_attempt_at=now,
                )
            )
    await db.commit()
    return list(rows)


async def mark_missed(
    db: AsyncSession,
    worker_id: str,
    grace_minutes: int = 15,
    now: datetime | None = None,
    tenant_id: str | None = None,
    campaign_id: str | None = None,
) -> int:
    now = now or datetime.now(UTC)
    query = select(CallbackRecord).where(
        CallbackRecord.state == "DUE",
        CallbackRecord.scheduled_at <= now - timedelta(minutes=grace_minutes),
    )
    if tenant_id is not None:
        query = query.where(CallbackRecord.tenant_id == tenant_id)
    if campaign_id is not None:
        query = query.where(CallbackRecord.campaign_id == campaign_id)
    rows = (await db.scalars(query.with_for_update(skip_locked=True))).all()
    for row in rows:
        row.state = row.desired_state = row.actual_state = "MISSED"
        row.version += 1
        db.add(
            CallbackEvent(
                id=uuid4(),
                callback_id=row.id,
                tenant_id=row.tenant_id,
                campaign_id=row.campaign_id,
                event_type="callback.missed",
                version=row.version,
                idempotency_key=f"callback:{row.id}:v{row.version}:missed",
                correlation_id=row.correlation_id,
                actor_id=worker_id,
                payload_json={"grace_minutes": grace_minutes},
            )
        )
    await db.commit()
    return len(rows)


async def reconcile(db: AsyncSession) -> dict[str, int]:
    orphan = (
        await db.scalars(
            select(CallbackRecord).where(
                CallbackRecord.assigned_agent_id.is_(None),
                CallbackRecord.assigned_team_id.is_(None),
            )
        )
    ).all()
    stale = (
        await db.scalars(
            select(CallbackDelivery)
            .join(CallbackRecord)
            .where(
                CallbackDelivery.callback_version < CallbackRecord.version,
                CallbackDelivery.status.in_(["QUEUED", "RETRY_PENDING"]),
            )
        )
    ).all()
    for item in stale:
        item.status = "STALE_CANCELLED"
        item.next_attempt_at = None
    await db.commit()
    return {"orphan_assignments": len(orphan), "stale_deliveries_cancelled": len(stale)}
