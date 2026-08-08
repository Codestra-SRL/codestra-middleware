import asyncio
import os
from typing import Any
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.social.domain import (
    Capability,
    NormalizedEvent,
    ProviderName,
    ProviderResult,
    SocialPostStatus,
)
from app.social.providers import SocialProviderAdapter, SocialProviderRegistry
from app.social.sql_repository import SqlSocialRepository
from app.social.queue import RedisSocialQueue
from app.workers.social import process_claimed_job
from app.integrations.hootsuite.exceptions import HootsuiteError
from app.integrations.hootsuite.oauth import HootsuiteOAuth
from app.social.hootsuite_oauth_state import HootsuiteOAuthStateRepository


DATABASE_URL = os.getenv("TEST_DATABASE_URL", "")
REDIS_URL = os.getenv("TEST_REDIS_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="TEST_DATABASE_URL is required"
)


class CountingPostlyAdapter(SocialProviderAdapter):
    name = ProviderName.POSTLY

    def __init__(self) -> None:
        self.calls = 0

    async def health_check(self) -> dict[str, Any]:
        return {"status": "HEALTHY"}

    def get_capabilities(self) -> frozenset[Capability]:
        return frozenset({Capability.POST_CREATE})

    async def create_post(self, post, account_refs, correlation_id):
        self.calls += 1
        return ProviderResult(f"staging-{post.id}", SocialPostStatus.DRAFT)


async def seed_account(session, tenant_id: UUID) -> UUID:
    account_id = uuid4()
    await session.execute(
        text("""INSERT INTO social_accounts
        (id,tenant_id,provider,provider_account_id,network,external_profile_name,
         external_profile_id,connection_state,capabilities,metadata)
        VALUES (:id,:tenant,'postly',:external,'other','synthetic staging account',
         :external,'connected','[]'::jsonb,'{"classification":"STAGING_SAFE"}'::jsonb)"""),
        {"id": account_id, "tenant": tenant_id, "external": f"synthetic-{account_id}"},
    )
    await session.commit()
    return account_id


def test_durable_idempotency_worker_and_event_outbox(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "postiz_delivery_enabled", True)

    async def scenario() -> None:
        engine = create_async_engine(DATABASE_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tenant_id = uuid4()
        key = f"phase2-{uuid4()}"
        correlation_id = f"phase2-correlation-{uuid4()}"
        async with factory() as session:
            account_id = await seed_account(session, tenant_id)
            repository = SqlSocialRepository(session)
            first = await repository.create_post_intent(
                tenant_id=tenant_id,
                provider=ProviderName.POSTLY,
                account_ids=(account_id,),
                content={"text": "CODESTRA STAGING DRAFT - NON-PRODUCTION"},
                campaign_id=None,
                publish_at=None,
                metadata={"classification": "STAGING_SAFE"},
                idempotency_key=key,
                correlation_id=correlation_id,
                request_id="phase2-request",
            )
            second = await repository.create_post_intent(
                tenant_id=tenant_id,
                provider=ProviderName.POSTLY,
                account_ids=(account_id,),
                content={"text": "CODESTRA STAGING DRAFT - NON-PRODUCTION"},
                campaign_id=None,
                publish_at=None,
                metadata={"classification": "STAGING_SAFE"},
                idempotency_key=key,
                correlation_id=correlation_id,
                request_id="phase2-request",
            )
            assert first[:2] == second[:2]
            assert first[2] is True and second[2] is False
            counts = (
                (
                    await session.execute(
                        text("""SELECT
                    (SELECT count(*) FROM social_posts WHERE tenant_id=:tenant) posts,
                    (SELECT count(*) FROM social_publish_jobs WHERE tenant_id=:tenant) jobs,
                    (SELECT count(*) FROM social_idempotency_records WHERE tenant_id=:tenant) keys,
                    (SELECT count(*) FROM social_audit_events WHERE tenant_id=:tenant) audits"""),
                        {"tenant": tenant_id},
                    )
                )
                .mappings()
                .one()
            )
            assert dict(counts) == {"posts": 1, "jobs": 1, "keys": 1, "audits": 1}
            updated = await repository.update_post(
                first[0],
                content={"text": "updated staging draft"},
                metadata={"classification": "STAGING_SAFE"},
                correlation_id="phase2-update-correlation",
                request_id="phase2-update-request",
            )
            assert updated.id == first[0]
            assert updated.content["text"] == "updated staging draft"
            assert (
                await session.scalar(
                    text("""SELECT count(*) FROM social_audit_events
                    WHERE social_post_id=:post AND action='POST_UPDATED'"""),
                    {"post": first[0]},
                )
                == 1
            )

        adapter = CountingPostlyAdapter()
        registry = SocialProviderRegistry()
        registry.register(adapter)
        async with factory() as session:
            jobs = await SqlSocialRepository(session).claim_jobs(
                worker_id="postly-social-01", limit=100, lease_seconds=60
            )
            own_job = next(item for item in jobs if UUID(str(item["id"])) == first[1])
            assert await process_claimed_job(session, registry, own_job) == "completed"
            assert adapter.calls == 1
            event_count = await session.scalar(
                text(
                    "SELECT count(*) FROM integration_event WHERE correlation_id=:correlation"
                ),
                {"correlation": correlation_id},
            )
            assert event_count == 1
        await engine.dispose()

    asyncio.run(scenario())


def test_database_failure_prevents_provider_dispatch():
    async def scenario() -> None:
        engine = create_async_engine(DATABASE_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        adapter = CountingPostlyAdapter()
        tenant_id = uuid4()
        async with factory() as session:
            with pytest.raises(Exception):
                await SqlSocialRepository(session).create_post_intent(
                    tenant_id=tenant_id,
                    provider=ProviderName.POSTLY,
                    account_ids=(uuid4(),),
                    content={"text": "must roll back"},
                    campaign_id=None,
                    publish_at=None,
                    metadata={},
                    idempotency_key=f"failure-{uuid4()}",
                    correlation_id="database-failure",
                    request_id="database-failure",
                )
            await session.rollback()
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM social_posts WHERE tenant_id=:tenant"),
                    {"tenant": tenant_id},
                )
                == 0
            )
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM outbox_event WHERE correlation_id='database-failure'"
                    )
                )
                == 0
            )
            assert adapter.calls == 0
        await engine.dispose()

    asyncio.run(scenario())


def test_webhook_receipt_is_persistently_deduplicated():
    async def scenario() -> None:
        engine = create_async_engine(DATABASE_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tenant_id = uuid4()
        subject_id = uuid4()
        provider_event_id = f"evt-{uuid4()}"
        event = NormalizedEvent(
            "social.post.published",
            ProviderName.POSTLY,
            subject_id,
            "webhook-correlation",
            tenant_id,
            {"status": "published"},
        )
        async with factory() as session:
            repository = SqlSocialRepository(session)
            first = await repository.persist_webhook(
                provider=ProviderName.POSTLY,
                provider_event_id=provider_event_id,
                payload_hash="a" * 64,
                correlation_id="webhook-correlation",
                event=event,
                safe_payload=event.payload,
            )
            second = await repository.persist_webhook(
                provider=ProviderName.POSTLY,
                provider_event_id=provider_event_id,
                payload_hash="a" * 64,
                correlation_id="webhook-correlation",
                event=event,
                safe_payload=event.payload,
            )
            assert first is True and second is False
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM social_webhook_events WHERE provider_event_id=:event"
                    ),
                    {"event": provider_event_id},
                )
                == 1
            )
        await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL is required")
def test_redis_loss_preserves_and_recovers_canonical_job():
    async def scenario() -> None:
        engine = create_async_engine(DATABASE_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        redis = Redis.from_url(REDIS_URL, decode_responses=True)
        await redis.flushdb()
        tenant_id = uuid4()
        async with factory() as session:
            account_id = await seed_account(session, tenant_id)
            repository = SqlSocialRepository(session)
            post_id, job_id, _ = await repository.create_post_intent(
                tenant_id=tenant_id,
                provider=ProviderName.POSTLY,
                account_ids=(account_id,),
                content={"text": "recoverable staging draft"},
                campaign_id=None,
                publish_at=None,
                metadata={},
                idempotency_key=f"redis-recovery-{uuid4()}",
                correlation_id="redis-recovery",
                request_id="redis-recovery",
            )
            queue = RedisSocialQueue(redis)
            await queue.enqueue(job_id, "redis-recovery")
            await redis.flushdb()
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM social_posts WHERE id=:post"),
                    {"post": post_id},
                )
                == 1
            )
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM social_publish_jobs WHERE id=:job"),
                    {"job": job_id},
                )
                == 1
            )
            signalable = await repository.signalable_jobs()
            recovered = next(item for item in signalable if item[0] == job_id)
            await queue.enqueue(*recovered)
            assert await redis.llen(queue.queue_key) == 1
        await redis.aclose()
        await engine.dispose()

    asyncio.run(scenario())


def test_hootsuite_oauth_state_is_durable_atomic_and_single_use():
    async def scenario() -> None:
        engine = create_async_engine(DATABASE_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        tenant_reference = f"tenant-phase3a-{uuid4()}"
        expired_tenant_reference = f"tenant-expired-{uuid4()}"
        oauth = HootsuiteOAuth(
            "synthetic-client",
            "synthetic-secret",
            "https://middleware.invalid/api/v1/social/oauth/hootsuite/callback",
            "synthetic-state-secret",
        )
        async with factory() as session:
            url = await oauth.persistent_authorization_url(
                tenant_reference, HootsuiteOAuthStateRepository(session)
            )
        from urllib.parse import parse_qs, urlparse

        state = parse_qs(urlparse(url).query)["state"][0]

        async with factory() as session:
            stored = (
                await session.execute(
                    text(
                        """SELECT state_hash, nonce_hash, tenant_reference, status
                        FROM hootsuite_oauth_states WHERE tenant_reference=:tenant"""
                    ),
                    {"tenant": tenant_reference},
                )
            ).one()
            assert stored.state_hash != state
            assert stored.nonce_hash not in state
            assert stored.tenant_reference == tenant_reference
            assert stored.status == "ISSUED"

        async def consume() -> str:
            restarted = HootsuiteOAuth(
                "synthetic-client",
                "synthetic-secret",
                "https://middleware.invalid/api/v1/social/oauth/hootsuite/callback",
                "synthetic-state-secret",
            )
            async with factory() as session:
                try:
                    return await restarted.verify_persistent_state(
                        state, HootsuiteOAuthStateRepository(session)
                    )
                except HootsuiteError:
                    return "REJECTED"

        results = await asyncio.gather(consume(), consume())
        assert sorted(results) == ["REJECTED", tenant_reference]

        assert await consume() == "REJECTED"

        tampered = state + "tampered"
        async with factory() as session:
            with pytest.raises(HootsuiteError):
                await oauth.verify_persistent_state(
                    tampered, HootsuiteOAuthStateRepository(session)
                )

        async with factory() as session:
            expired_url = await oauth.persistent_authorization_url(
                expired_tenant_reference, HootsuiteOAuthStateRepository(session)
            )
            expired_state = parse_qs(urlparse(expired_url).query)["state"][0]
            await session.execute(
                text(
                    """UPDATE hootsuite_oauth_states SET expires_at=now()-interval '1 second'
                        WHERE tenant_reference=:tenant"""
                ),
                {"tenant": expired_tenant_reference},
            )
            await session.commit()
        async with factory() as session:
            with pytest.raises(HootsuiteError):
                await oauth.verify_persistent_state(
                    expired_state, HootsuiteOAuthStateRepository(session)
                )

        async with factory() as session:
            await session.execute(
                text("""INSERT INTO hootsuite_oauth_states
                (state_hash,tenant_reference,nonce_hash,issued_at,expires_at,status)
                VALUES (:hash,:tenant,'0',now()-interval '20 minutes',
                now()-interval '10 minutes','ISSUED')"""),
                {"hash": uuid4().hex.ljust(64, "0"), "tenant": f"expired-{uuid4()}"},
            )
            await session.commit()
            assert await HootsuiteOAuthStateRepository(session).expire() == 2
        await engine.dispose()

    asyncio.run(scenario())
