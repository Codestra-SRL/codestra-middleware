import asyncio
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.social_repository import SocialRepository


def test_durable_social_control_plane_lifecycle():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert any(marker in database_url for marker in ("test", "diag", "rehearsal"))
    asyncio.run(_scenario(database_url))


async def _scenario(database_url: str) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)  # noqa: UP017
    try:
        async with factory() as session:
            await session.execute(
                text(
                    "TRUNCATE social_reconciliation_lease,social_dead_letter,"
                    "social_delivery_attempt,social_audit_record,"
                    "social_idempotency_claim,social_publication,social_approval,"
                    "social_content_version,social_content_job"
                )
            )
            await session.commit()
            repository = SocialRepository(session)
            await repository.create_job(
                {
                    "organization_id": "ORG-CODESTRA",
                    "workspace_id": "WS-TEST",
                    "campaign_id": "CMP-TEST",
                    "content_job_id": "JOB-DURABLE-TEST",
                    "content_version": 1,
                    "preferred_language": "en",
                    "correlation_id": "COR-DURABLE-TEST",
                    "scheduled_at": datetime(
                        2026,
                        8,
                        3,
                        12,
                        tzinfo=timezone.utc,  # noqa: UP017
                    ),
                }
            )
            await repository.store_proposal(
                "JOB-DURABLE-TEST",
                {
                    "content_job_id": "JOB-DURABLE-TEST",
                    "content_version": 1,
                    "language": "en",
                    "caption": "private mock content",
                    "status": "proposal_only",
                },
                "N8N-MOCK-1",
            )
            await repository.approve(
                "JOB-DURABLE-TEST",
                {
                    "approval_id": "APR-DURABLE-TEST",
                    "approved_by": "USR-TEST",
                    "approved_at": now,
                    "content_version": 1,
                },
            )
            first = await repository.claim_publications(
                "JOB-DURABLE-TEST", ["INT-TEST-A", "INT-TEST-B"]
            )
            duplicate = await repository.claim_publications(
                "JOB-DURABLE-TEST", ["INT-TEST-A", "INT-TEST-B"]
            )
            assert [item["id"] for item in first] == [item["id"] for item in duplicate]
            assert (
                await repository.record_failure(
                    first[0]["id"],
                    category="permanent_provider",
                    code="PROVIDER_REJECTED",
                    retryable=False,
                )
                == "dead_letter"
            )
            await repository.require_reconciliation(first[1]["id"])
            lease = await repository.claim_reconciliation("test-worker")
            assert lease and lease["lease_owner"] == "test-worker"
            assert (
                await session.execute(
                    text("SELECT count(*) FROM social_idempotency_claim")
                )
            ).scalar_one() == 2
            assert (
                await session.execute(text("SELECT count(*) FROM social_dead_letter"))
            ).scalar_one() == 1
    finally:
        await engine.dispose()
