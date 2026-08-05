"""One-cycle durable workflow task worker primitives."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CLAIM = text("""
WITH candidate AS (
 SELECT public_id FROM ai_workflow_tasks
 WHERE state IN ('QUEUED','RETRY_SCHEDULED')
   AND (available_at IS NULL OR available_at <= :now)
   AND (lease_expires_at IS NULL OR lease_expires_at < :now)
 ORDER BY available_at NULLS FIRST, created_at
 FOR UPDATE SKIP LOCKED LIMIT :limit
)
UPDATE ai_workflow_tasks task SET state='RUNNING', state_version=state_version+1,
 lease_owner=:owner, lease_expires_at=:lease_expires, updated_at=:now
FROM candidate WHERE task.public_id=candidate.public_id
RETURNING task.public_id,task.workflow_public_id,task.state_version,task.payload_json
""")


async def claim_tasks(
    session: AsyncSession,
    owner: str,
    limit: int = 1,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> list[dict]:
    if not owner or limit not in range(1, 11) or lease_seconds not in range(10, 601):
        raise ValueError("bounded worker lease required")
    current = now or datetime.now(UTC)
    rows = (
        (
            await session.execute(
                CLAIM,
                {
                    "owner": owner,
                    "limit": limit,
                    "now": current,
                    "lease_expires": current + timedelta(seconds=lease_seconds),
                },
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def recover_expired_leases(
    session: AsyncSession, now: datetime | None = None
) -> int:
    current = now or datetime.now(UTC)
    result = await session.execute(
        text(
            "UPDATE ai_workflow_tasks SET state='RETRY_SCHEDULED',lease_owner=NULL,lease_expires_at=NULL,available_at=:next,updated_at=:now WHERE state='RUNNING' AND lease_expires_at<:now"
        ),
        {"now": current, "next": current + timedelta(seconds=30)},
    )
    return cast(int, getattr(result, "rowcount", 0))


def new_worker_identity() -> str:
    return f"ai-workflow-worker-{uuid4().hex}"
