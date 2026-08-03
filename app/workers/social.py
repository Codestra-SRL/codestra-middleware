"""Durable social delivery and recovery worker primitives."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def claim_delivery(
    session: AsyncSession, owner: str, lease_seconds: int = 60
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                text("""
        WITH candidate AS (
          SELECT id FROM social_publication
          WHERE state IN ('queued','retry_wait')
            AND COALESCE(next_attempt_at,now())<=now()
            AND (lease_expires_at IS NULL OR lease_expires_at<=now())
          ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
        ) UPDATE social_publication p SET state='leased',lease_owner=:owner,
          lease_expires_at=now()+make_interval(secs=>:seconds),updated_at=now()
        FROM candidate WHERE p.id=candidate.id RETURNING p.*
    """),
                {"owner": owner, "seconds": lease_seconds},
            )
        )
        .mappings()
        .one_or_none()
    )
    await session.commit()
    return dict(row) if row else None


async def complete_mock_delivery(session: AsyncSession, publication_id: UUID) -> None:
    await session.execute(
        text("""
        UPDATE social_publication SET state='scheduled',postly_group_id=:group_id,
          provider_result=CAST(:result AS jsonb),lease_owner=NULL,lease_expires_at=NULL,
          updated_at=now() WHERE id=:id AND state='leased'
    """),
        {
            "id": publication_id,
            "group_id": f"mock-{publication_id}",
            "result": '{"state":"scheduled","mock":true}',
        },
    )
    await session.execute(
        text("""
        UPDATE social_content_job j SET state='scheduled',updated_at=now()
        WHERE j.id=(SELECT job_id FROM social_publication WHERE id=:id)
          AND NOT EXISTS (
            SELECT 1 FROM social_publication p
            WHERE p.job_id=j.id AND p.state<>'scheduled'
          )
    """),
        {"id": publication_id},
    )
    await session.commit()


async def recover_expired_delivery_leases(session: AsyncSession) -> int:
    result = await session.execute(
        text("""
        UPDATE social_publication SET state='retry_wait',lease_owner=NULL,
          lease_expires_at=NULL,next_attempt_at=now(),updated_at=now()
        WHERE state='leased' AND lease_expires_at<=now()
    """)
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0))


async def dead_letter_depth(session: AsyncSession) -> int:
    return int(
        (
            await session.execute(
                text(
                    "SELECT count(*) FROM social_dead_letter WHERE replayed_at IS NULL"
                )
            )
        ).scalar_one()
    )


async def replay_one_dead_letter(
    session: AsyncSession, *, authorized: bool = False
) -> UUID | None:
    if not authorized:
        raise PermissionError("social dead-letter replay is not authorized")
    row = (
        (
            await session.execute(
                text("""
            SELECT d.id,d.publication_id FROM social_dead_letter d
            JOIN social_publication p ON p.id=d.publication_id
            WHERE d.replayed_at IS NULL AND p.state='dead_letter'
            ORDER BY d.dead_lettered_at FOR UPDATE SKIP LOCKED LIMIT 1
            """)
            )
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        return None
    await session.execute(
        text("""
        UPDATE social_dead_letter SET replay_count=replay_count+1,replayed_at=now()
        WHERE id=:dead_letter_id
        """),
        {"dead_letter_id": row["id"]},
    )
    await session.execute(
        text("""
        UPDATE social_publication SET state='retry_wait',next_attempt_at=now(),
          lease_owner=NULL,lease_expires_at=NULL,updated_at=now()
        WHERE id=:publication_id
        """),
        {"publication_id": row["publication_id"]},
    )
    await session.commit()
    return row["publication_id"]


async def recover_expired_reconciliation_leases(session: AsyncSession) -> int:
    result = await session.execute(
        text("""
        UPDATE social_reconciliation_lease SET status='retry_wait',lease_owner=NULL,
          lease_expires_at=NULL,next_attempt_at=:now,updated_at=:now
        WHERE status='leased' AND lease_expires_at<=:now
    """),
        {"now": datetime.now(timezone.utc)},  # noqa: UP017
    )
    await session.commit()
    return int(getattr(result, "rowcount", 0))
