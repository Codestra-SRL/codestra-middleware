from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class HootsuiteOAuthStateRepository:
    """Durable, hash-only OAuth state ledger with atomic single-use consumption."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def persist(
        self,
        *,
        state: str,
        tenant_reference: str,
        nonce: str,
        issued_at: datetime,
        ttl_seconds: int,
    ) -> None:
        await self.session.execute(
            text("""INSERT INTO hootsuite_oauth_states
            (state_hash,tenant_reference,nonce_hash,issued_at,expires_at,status)
            VALUES (:state_hash,:tenant,:nonce_hash,:issued,:expires,'ISSUED')"""),
            {
                "state_hash": hashlib.sha256(state.encode()).hexdigest(),
                "tenant": tenant_reference,
                "nonce_hash": hashlib.sha256(nonce.encode()).hexdigest(),
                "issued": issued_at,
                "expires": issued_at + timedelta(seconds=ttl_seconds),
            },
        )
        await self.session.commit()

    async def consume(self, *, state: str, tenant_reference: str) -> bool:
        row = await self.session.scalar(
            text("""UPDATE hootsuite_oauth_states
            SET consumed_at=now(), status='CONSUMED'
            WHERE state_hash=:state_hash AND tenant_reference=:tenant
              AND status='ISSUED' AND consumed_at IS NULL AND expires_at > now()
            RETURNING state_hash"""),
            {
                "state_hash": hashlib.sha256(state.encode()).hexdigest(),
                "tenant": tenant_reference,
            },
        )
        await self.session.commit()
        return row is not None

    async def expire(self) -> int:
        result = await self.session.execute(
            text("""UPDATE hootsuite_oauth_states SET status='EXPIRED'
            WHERE status='ISSUED' AND expires_at <= :now"""),
            {"now": datetime.now(timezone.utc)},
        )
        await self.session.commit()
        return int(getattr(result, "rowcount", 0) or 0)
