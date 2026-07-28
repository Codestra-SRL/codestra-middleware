import asyncio
import os
from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.campaign_design import (
    CampaignDesignInput,
    CampaignDesignService,
    DesignConflict,
    PostgresDesignStore,
)


def _database_url() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL", "")
    if not database_url:
        pytest.skip("requires an explicitly provisioned disposable database")
    assert "diag" in database_url or "rehearsal" in database_url
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )
    return database_url


def _run(scenario: Callable[[AsyncEngine, async_sessionmaker[AsyncSession]], Awaitable[None]]):
    async def execute():
        engine = create_async_engine(_database_url())
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                await session.execute(
                    text(
                        "TRUNCATE campaign_design_approval,"
                        "campaign_design_failure,campaign_event_inbox,"
                        "campaign_resource_allocation,campaign_design_current,"
                        "campaign_design_revision"
                    )
                )
                await session.commit()
            await scenario(engine, factory)
        finally:
            await engine.dispose()

    asyncio.run(execute())


def _request(index: int = 1, **changes) -> CampaignDesignInput:
    values = {
        "event_id": f"diag-odoo-event-{uuid4()}",
        "integration_uuid": str(uuid4()),
        "odoo_campaign_id": 910000 + index,
        "environment": "staging",
        "business_unit": "TEST",
        "purpose": f"E{index:02d}",
        "direction": "outbound",
        "owner_user_id": 9101,
        "supervisor_user_id": 9102,
        "correlation_id": f"diag-correlation-{uuid4()}",
        "design_configuration": {
            "time_zone": "America/Santo_Domingo",
            "calling_hour_start": 9.0,
            "calling_hour_end": 17.0,
            "consent_required": True,
            "dnc_enforced": True,
            "team_ids": [9101],
            "supervisor_ids": [9102],
        },
    }
    values.update(changes)
    return CampaignDesignInput(**values)


async def _consume(
    factory: async_sessionmaker[AsyncSession],
    item: CampaignDesignInput,
    *,
    fault: str | None = None,
    max_attempts: int = 3,
):
    def fault_hook(point: str):
        if point == fault:
            raise RuntimeError(f"fault:{point}")

    async with factory() as session:
        return await CampaignDesignService(
            PostgresDesignStore(session, fault_hook=fault_hook if fault else None)
        ).consume(item, max_attempts=max_attempts)


async def _counts(
    factory: async_sessionmaker[AsyncSession], item: CampaignDesignInput
) -> dict[str, int]:
    async with factory() as session:
        result = {}
        for key, table, predicate in (
            ("receipts", "campaign_event_inbox", "event_id=:event"),
            (
                "revisions",
                "campaign_design_revision",
                "integration_uuid=:uuid",
            ),
            (
                "allocations",
                "campaign_resource_allocation",
                "integration_uuid=:uuid",
            ),
            (
                "audits",
                "audit_event",
                "subject=:uuid AND action='campaign.design.consumed'",
            ),
        ):
            result[key] = int(
                await session.scalar(
                    text(f"SELECT count(*) FROM {table} WHERE {predicate}"),
                    {"event": item.event_id, "uuid": item.integration_uuid},
                )
            )
        return result


async def _make_retry_due(
    factory: async_sessionmaker[AsyncSession], event_id: str
) -> None:
    async with factory() as session:
        await session.execute(
            text(
                "UPDATE campaign_design_failure SET next_attempt_at=now() "
                "WHERE event_id=:event AND status='retry'"
            ),
            {"event": event_id},
        )
        await session.commit()


def test_successful_consumption_commits_receipt_design_allocation_and_audit():
    async def scenario(_engine, factory):
        item = _request()
        result = await _consume(factory, item)
        assert result["idempotent_replay"] is False
        assert await _counts(factory, item) == {
            "receipts": 1,
            "revisions": 1,
            "allocations": 1,
            "audits": 1,
        }
        async with factory() as session:
            receipt = (
                await session.execute(
                    text(
                        "SELECT processing_state,result_revision,committed_at "
                        "FROM campaign_event_inbox WHERE event_id=:event"
                    ),
                    {"event": item.event_id},
                )
            ).mappings().one()
            assert receipt["processing_state"] == "completed"
            assert receipt["result_revision"] == 1
            assert receipt["committed_at"] is not None

    _run(scenario)


@pytest.mark.parametrize(
    "fault", ["after_receipt", "after_allocation", "after_revision", "before_commit"]
)
def test_failure_before_commit_rolls_back_every_business_record(fault):
    async def scenario(_engine, factory):
        item = _request()
        with pytest.raises(RuntimeError, match=f"fault:{fault}"):
            await _consume(factory, item, fault=fault)
        assert await _counts(factory, item) == {
            "receipts": 0,
            "revisions": 0,
            "allocations": 0,
            "audits": 0,
        }
        async with factory() as session:
            failure = (
                await session.execute(
                    text(
                        "SELECT attempts,status FROM campaign_design_failure "
                        "WHERE event_id=:event"
                    ),
                    {"event": item.event_id},
                )
            ).one()
            assert tuple(failure) == (1, "retry")
        await _make_retry_due(factory, item.event_id)
        recovered = await _consume(factory, item)
        assert recovered["idempotent_replay"] is False
        assert await _counts(factory, item) == {
            "receipts": 1,
            "revisions": 1,
            "allocations": 1,
            "audits": 1,
        }

    _run(scenario)


def test_failure_after_commit_before_ack_replays_saved_result():
    async def scenario(_engine, factory):
        item = _request()
        committed = await _consume(factory, item)
        with pytest.raises(RuntimeError, match="synthetic ACK crash"):
            raise RuntimeError("synthetic ACK crash")
        replay = await _consume(factory, item)
        assert replay["idempotent_replay"] is True
        assert replay["vicidial"] == committed["vicidial"]
        assert await _counts(factory, item) == {
            "receipts": 1,
            "revisions": 1,
            "allocations": 1,
            "audits": 1,
        }

    _run(scenario)


def test_concurrent_duplicate_delivery_has_one_committed_outcome():
    async def scenario(_engine, factory):
        item = _request()
        first, second = await asyncio.gather(
            _consume(factory, item), _consume(factory, item)
        )
        assert {first["idempotent_replay"], second["idempotent_replay"]} == {
            False,
            True,
        }
        assert first["vicidial"] == second["vicidial"]
        assert await _counts(factory, item) == {
            "receipts": 1,
            "revisions": 1,
            "allocations": 1,
            "audits": 1,
        }

    _run(scenario)


def test_concurrent_distinct_events_serialize_on_new_integration():
    async def scenario(_engine, factory):
        first = _request(purpose="FIRST")
        second = first.model_copy(
            update={
                "event_id": f"diag-odoo-event-{uuid4()}",
                "purpose": "SECOND",
                "correlation_id": f"diag-correlation-{uuid4()}",
            }
        )
        outcomes = await asyncio.gather(
            _consume(factory, first),
            _consume(factory, second),
            return_exceptions=True,
        )
        assert sum(isinstance(value, dict) for value in outcomes) == 1
        assert sum(isinstance(value, DesignConflict) for value in outcomes) == 1
        async with factory() as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM campaign_design_revision "
                        "WHERE integration_uuid=:uuid"
                    ),
                    {"uuid": first.integration_uuid},
                )
                == 1
            )

    _run(scenario)


def test_changed_payload_for_committed_event_is_a_conflict():
    async def scenario(_engine, factory):
        item = _request()
        await _consume(factory, item)
        with pytest.raises(DesignConflict, match="event replay payload conflict"):
            await _consume(
                factory, item.model_copy(update={"purpose": "CHANGED"})
            )
        assert await _counts(factory, item) == {
            "receipts": 1,
            "revisions": 1,
            "allocations": 1,
            "audits": 1,
        }

    _run(scenario)


def test_dead_letter_occurs_only_at_configured_retry_limit():
    async def scenario(_engine, factory):
        item = _request()
        for attempt in range(1, 4):
            if attempt > 1:
                await _make_retry_due(factory, item.event_id)
            with pytest.raises(RuntimeError):
                await _consume(
                    factory, item, fault="after_receipt", max_attempts=3
                )
            async with factory() as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT attempts,status FROM campaign_design_failure "
                            "WHERE event_id=:event"
                        ),
                        {"event": item.event_id},
                    )
                ).one()
                assert row.attempts == attempt
                assert row.status == (
                    "dead_letter" if attempt == 3 else "retry"
                )
        assert await _counts(factory, item) == {
            "receipts": 0,
            "revisions": 0,
            "allocations": 0,
            "audits": 0,
        }
        with pytest.raises(DesignConflict, match="dead-lettered"):
            await _consume(factory, item)
        async with factory() as session:
            attempts = await session.scalar(
                text(
                    "SELECT attempts FROM campaign_design_failure "
                    "WHERE event_id=:event"
                ),
                {"event": item.event_id},
            )
            assert attempts == 3

    _run(scenario)


def test_retry_before_persisted_backoff_expires_is_rejected():
    async def scenario(_engine, factory):
        item = _request()
        with pytest.raises(RuntimeError):
            await _consume(factory, item, fault="after_receipt")
        with pytest.raises(DesignConflict, match="retry is deferred"):
            await _consume(factory, item)
        async with factory() as session:
            attempts = await session.scalar(
                text(
                    "SELECT attempts FROM campaign_design_failure "
                    "WHERE event_id=:event"
                ),
                {"event": item.event_id},
            )
            assert attempts == 1

    _run(scenario)


async def _approve(
    factory: async_sessionmaker[AsyncSession],
    item: CampaignDesignInput,
    preview: dict,
    *,
    actor: str = "staging-supervisor",
    reason: str = "approved for staging source validation",
    idempotency_key: str = "approval-idempotency-0001",
    correlation_id: str | None = None,
    revision: int | None = None,
    manifest_hash: str | None = None,
):
    async with factory() as session:
        return await CampaignDesignService(PostgresDesignStore(session)).approve(
            item.integration_uuid,
            revision or preview["design_revision"],
            manifest_hash or preview["manifest_hash"],
            actor,
            reason,
            idempotency_key,
            correlation_id or item.correlation_id,
        )


def test_first_approval_and_identical_replay_preserve_provenance():
    async def scenario(_engine, factory):
        item = _request()
        preview = await _consume(factory, item)
        first = await _approve(factory, item, preview)
        second = await _approve(factory, item, preview)
        assert first["approval"] == second["approval"]
        async with factory() as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM campaign_design_approval "
                        "WHERE integration_uuid=:uuid"
                    ),
                    {"uuid": item.integration_uuid},
                )
                == 1
            )

    _run(scenario)


@pytest.mark.parametrize(
    "change",
    [
        {"actor": "another-supervisor"},
        {"reason": "a materially different approval reason"},
        {"revision": 2},
        {"manifest_hash": "0" * 64},
    ],
)
def test_approval_provenance_conflicts_cannot_overwrite(change):
    async def scenario(_engine, factory):
        item = _request()
        preview = await _consume(factory, item)
        original = await _approve(factory, item, preview)
        with pytest.raises(DesignConflict):
            await _approve(
                factory,
                item,
                preview,
                idempotency_key="approval-idempotency-conflict",
                **change,
            )
        replay = await _approve(factory, item, preview)
        assert replay["approval"] == original["approval"]

    _run(scenario)


def test_concurrent_approvals_allow_exactly_one_winner():
    async def scenario(_engine, factory):
        item = _request()
        preview = await _consume(factory, item)
        outcomes = await asyncio.gather(
            _approve(
                factory,
                item,
                preview,
                actor="supervisor-one",
                idempotency_key="approval-concurrent-one",
            ),
            _approve(
                factory,
                item,
                preview,
                actor="supervisor-two",
                idempotency_key="approval-concurrent-two",
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(value, dict) for value in outcomes) == 1
        assert sum(isinstance(value, DesignConflict) for value in outcomes) == 1

    _run(scenario)


def test_concurrent_identical_approval_replays_the_committed_record():
    async def scenario(_engine, factory):
        item = _request()
        preview = await _consume(factory, item)
        first, second = await asyncio.gather(
            _approve(factory, item, preview),
            _approve(factory, item, preview),
        )
        assert first["approval"] == second["approval"]
        async with factory() as session:
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM campaign_design_approval "
                        "WHERE integration_uuid=:uuid"
                    ),
                    {"uuid": item.integration_uuid},
                )
                == 1
            )

    _run(scenario)


def test_concurrent_global_approval_idempotency_key_conflicts_cleanly():
    async def scenario(_engine, factory):
        first_item = _request(index=1)
        second_item = _request(index=2)
        first_preview = await _consume(factory, first_item)
        second_preview = await _consume(factory, second_item)
        outcomes = await asyncio.gather(
            _approve(
                factory,
                first_item,
                first_preview,
                idempotency_key="approval-global-concurrent-key",
            ),
            _approve(
                factory,
                second_item,
                second_preview,
                idempotency_key="approval-global-concurrent-key",
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(value, dict) for value in outcomes) == 1
        assert sum(isinstance(value, DesignConflict) for value in outcomes) == 1

    _run(scenario)


def test_approved_manifest_is_immutable_and_new_revision_needs_approval():
    async def scenario(_engine, factory):
        item = _request()
        first_preview = await _consume(factory, item)
        await _approve(factory, item, first_preview)
        async with factory() as session:
            with pytest.raises(Exception, match="immutable"):
                await session.execute(
                    text(
                        "UPDATE campaign_design_revision "
                        "SET manifest=CAST(:manifest AS jsonb) "
                        "WHERE integration_uuid=:uuid AND revision=1"
                    ),
                    {"manifest": "{}", "uuid": item.integration_uuid},
                )
            await session.rollback()

        revised = item.model_copy(
            update={
                "event_id": f"diag-odoo-event-{uuid4()}",
                "purpose": "REV2",
            }
        )
        second_preview = await _consume(factory, revised)
        assert second_preview["design_revision"] == 2
        assert second_preview["approval"]["state"] == "preview"
        await _approve(
            factory,
            revised,
            second_preview,
            idempotency_key="approval-revision-two",
        )
        async with factory() as session:
            approvals = (
                await session.execute(
                    text(
                        "SELECT design_revision FROM campaign_design_approval "
                        "WHERE integration_uuid=:uuid ORDER BY design_revision"
                    ),
                    {"uuid": item.integration_uuid},
                )
            ).scalars().all()
            assert approvals == [1, 2]
            assert (
                await session.scalar(
                    text(
                        "SELECT count(*) FROM audit_event "
                        "WHERE subject=:uuid "
                        "AND action='campaign.design.approved'"
                    ),
                    {"uuid": item.integration_uuid},
                )
                == 2
            )

    _run(scenario)


def test_design_can_return_to_an_earlier_payload_as_a_new_revision():
    async def scenario(_engine, factory):
        original = _request(purpose="ORIGINAL")
        first = await _consume(factory, original)
        await _approve(factory, original, first)

        changed = original.model_copy(
            update={
                "event_id": f"diag-odoo-event-{uuid4()}",
                "purpose": "CHANGED",
                "correlation_id": f"diag-correlation-{uuid4()}",
            }
        )
        second = await _consume(factory, changed)
        await _approve(
            factory,
            changed,
            second,
            idempotency_key="approval-revision-two-changed",
        )

        restored = original.model_copy(
            update={
                "event_id": f"diag-odoo-event-{uuid4()}",
                "correlation_id": f"diag-correlation-{uuid4()}",
            }
        )
        third = await _consume(factory, restored)
        assert third["design_revision"] == 3
        assert third["approval"]["state"] == "preview"
        assert third["manifest_hash"] != first["manifest_hash"]

        async with factory() as session:
            revisions = (
                await session.execute(
                    text(
                        "SELECT revision,payload_hash FROM campaign_design_revision "
                        "WHERE integration_uuid=:uuid ORDER BY revision"
                    ),
                    {"uuid": original.integration_uuid},
                )
            ).all()
            assert [revision for revision, _ in revisions] == [1, 2, 3]
            assert revisions[0].payload_hash == revisions[2].payload_hash

    _run(scenario)
