"""PostgreSQL-authoritative enterprise event delivery operations."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def materialize_deliveries(db: AsyncSession, event_id: UUID) -> int:
    result = await db.execute(
        text("""
            INSERT INTO enterprise_event_delivery (
                id, event_id, subscription_id, tenant_id, workspace_id, status
            )
            SELECT gen_random_uuid(), event.id, subscription.id,
                   event.tenant_id, event.workspace_id, 'PENDING'
            FROM enterprise_event event
            JOIN enterprise_event_subscription subscription
              ON subscription.tenant_id=event.tenant_id
             AND subscription.workspace_id=event.workspace_id
             AND subscription.enabled
             AND event.event_type LIKE replace(subscription.event_type_pattern, '*', '%')
            WHERE event.id=:event_id
            ON CONFLICT (event_id, subscription_id) DO NOTHING
        """),
        {"event_id": event_id},
    )
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


async def claim_deliveries(
    db: AsyncSession,
    *,
    worker_id: str,
    limit: int = 50,
    lease_seconds: int = 60,
) -> list[dict[str, object]]:
    rows = (await db.execute(
        text("""
            WITH candidates AS (
                SELECT delivery.id
                FROM enterprise_event_delivery delivery
                WHERE (
                    delivery.status IN ('PENDING','RETRY')
                    OR (delivery.status='LEASED' AND delivery.lease_expires_at < now())
                )
                  AND delivery.next_attempt_at <= now()
                ORDER BY delivery.next_attempt_at, delivery.created_at, delivery.id
                FOR UPDATE SKIP LOCKED
                LIMIT :limit
            )
            UPDATE enterprise_event_delivery delivery
            SET status='LEASED', lease_owner=:worker_id,
                lease_expires_at=now() + make_interval(secs => :lease_seconds),
                attempts=delivery.attempts + 1, updated_at=now()
            FROM candidates
            WHERE delivery.id=candidates.id
            RETURNING delivery.id, delivery.event_id, delivery.subscription_id,
                      delivery.tenant_id, delivery.workspace_id, delivery.attempts
        """),
        {"worker_id": worker_id, "limit": limit, "lease_seconds": lease_seconds},
    )).mappings().all()
    await db.commit()
    return [dict(row) for row in rows]


async def complete_delivery(db: AsyncSession, delivery_id: UUID, worker_id: str) -> bool:
    result = await db.execute(
        text("""
            UPDATE enterprise_event_delivery
            SET status='DELIVERED', lease_owner=NULL, lease_expires_at=NULL, updated_at=now()
            WHERE id=:id AND status='LEASED' AND lease_owner=:worker_id
        """),
        {"id": delivery_id, "worker_id": worker_id},
    )
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0) == 1


async def fail_delivery(
    db: AsyncSession,
    delivery_id: UUID,
    worker_id: str,
    error_code: str,
    max_attempts: int,
) -> str | None:
    row = (await db.execute(
        text("""
            UPDATE enterprise_event_delivery
            SET status=CASE WHEN attempts >= :max_attempts THEN 'DEAD_LETTER' ELSE 'RETRY' END,
                next_attempt_at=CASE WHEN attempts >= :max_attempts THEN next_attempt_at
                    ELSE now() + make_interval(secs => LEAST(300, (2 ^ attempts)::integer)) END,
                lease_owner=NULL, lease_expires_at=NULL, last_error_code=:error_code, updated_at=now()
            WHERE id=:id AND status='LEASED' AND lease_owner=:worker_id
            RETURNING status
        """),
        {
            "id": delivery_id,
            "worker_id": worker_id,
            "error_code": error_code[:64],
            "max_attempts": min(max(max_attempts, 1), 10),
        },
    )).scalar_one_or_none()
    await db.commit()
    return row


async def process_replays(db: AsyncSession, *, limit: int = 50) -> int:
    """Atomically requeue deliveries for approved replay requests."""
    result = await db.execute(
        text("""
            WITH requested AS (
                SELECT replay.id, replay.event_id
                FROM enterprise_event_replay replay
                WHERE replay.status='PENDING'
                ORDER BY replay.requested_at, replay.id
                FOR UPDATE SKIP LOCKED
                LIMIT :limit
            ), requeued AS (
                UPDATE enterprise_event_delivery delivery
                SET status='RETRY', attempts=0, next_attempt_at=now(),
                    lease_owner=NULL, lease_expires_at=NULL,
                    last_error_code=NULL, updated_at=now()
                FROM requested
                WHERE delivery.event_id=requested.event_id
                RETURNING requested.id
            )
            UPDATE enterprise_event_replay replay
            SET status='COMPLETED', updated_at=now()
            WHERE replay.id IN (SELECT id FROM requested)
            RETURNING replay.id
        """),
        {"limit": limit},
    )
    rows = result.scalars().all()
    await db.commit()
    return len(rows)


async def retry_dead_letter(
    db: AsyncSession, delivery_id: UUID, *, tenant_id: UUID, workspace_id: UUID
) -> bool:
    result = await db.execute(
        text("""
            UPDATE enterprise_event_delivery
            SET status='RETRY', attempts=0, next_attempt_at=now(),
                lease_owner=NULL, lease_expires_at=NULL,
                last_error_code=NULL, updated_at=now()
            WHERE id=:id AND tenant_id=:tenant_id AND workspace_id=:workspace_id
              AND status='DEAD_LETTER'
        """),
        {"id": delivery_id, "tenant_id": tenant_id, "workspace_id": workspace_id},
    )
    await db.commit()
    return int(getattr(result, "rowcount", 0) or 0) == 1
