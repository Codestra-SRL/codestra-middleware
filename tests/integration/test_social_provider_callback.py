import asyncio
import hashlib
import hmac
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.social_repository import SocialRepository
from app.db.session import get_session
from app.main import app


def test_signed_social_callback_http_flow(monkeypatch):
    database_url = os.environ.get("TEST_DATABASE_URL")
    secret_file = os.environ.get("TEST_CALLBACK_SECRET_FILE")
    if not database_url or not secret_file:
        pytest.skip("requires disposable PostgreSQL and callback secret file")
    assert any(marker in database_url for marker in ("test", "diag", "rehearsal"))
    asyncio.run(_scenario(monkeypatch, database_url, secret_file))


async def _scenario(monkeypatch, database_url: str, secret_file: str) -> None:
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def session_override():
        async with factory() as session:
            yield session

    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "middleware_secret", "synthetic-api-secret")
    monkeypatch.setattr(settings, "social_control_plane_enabled", True)
    monkeypatch.setattr(settings, "social_mock_adapter_enabled", True)
    monkeypatch.setattr(settings, "postly_adapter_enabled", False)
    monkeypatch.setattr(settings, "postly_callback_hmac_file", secret_file)
    monkeypatch.setattr(settings, "postly_callback_source_cidrs", "127.0.0.0/8")
    app.dependency_overrides[get_session] = session_override
    job_id = f"CALLBACK-JOB-{uuid4()}"
    release_id = f"RELEASE-{uuid4()}"
    group_id = f"GROUP-{uuid4()}"
    try:
        async with factory() as session:
            repository = SocialRepository(session)
            await repository.create_job(
                {
                    "organization_id": "ORG-CALLBACK-TEST",
                    "workspace_id": "WS-CALLBACK-TEST",
                    "campaign_id": "CMP-CALLBACK-TEST",
                    "content_job_id": job_id,
                    "content_version": 1,
                    "integration_ids": ["INT-CALLBACK-TEST"],
                    "preferred_language": "en",
                    "correlation_id": "COR-CALLBACK-TEST",
                    "scheduled_at": datetime(2026, 8, 4, 12, tzinfo=UTC),
                }
            )
            await repository.store_proposal(
                job_id,
                {
                    "content_job_id": job_id,
                    "content_version": 1,
                    "language": "en",
                    "caption": "private synthetic callback content",
                    "status": "proposal_only",
                    "hashtags": [],
                    "warnings": [],
                },
                "N8N-CALLBACK-TEST",
                "ORG-CALLBACK-TEST",
                "WS-CALLBACK-TEST",
            )
            await repository.approve(
                job_id,
                {
                    "approval_id": f"APR-{uuid4()}",
                    "approved_by": "USR-CALLBACK-TEST",
                    "approved_at": datetime.now(UTC),
                    "content_version": 1,
                },
                "ORG-CALLBACK-TEST",
                "WS-CALLBACK-TEST",
            )
            publications = await repository.claim_publications(
                job_id,
                ["INT-CALLBACK-TEST"],
                "ORG-CALLBACK-TEST",
                "WS-CALLBACK-TEST",
            )
            await repository.record_result(
                publications[0]["id"],
                {
                    "state": "scheduled",
                    "postly_group_id": group_id,
                    "provider_release_id": release_id,
                },
            )

        callback_id = uuid4()
        event_id = f"EVENT-{uuid4()}"
        payload = {
            "callback_id": str(callback_id),
            "attempt": 1,
            "event_id": event_id,
            "correlation_id": "COR-CALLBACK-TEST",
            "state": "published",
            "occurred_at": datetime.now(UTC).isoformat(),
            "postly_group_id": group_id,
            "provider_results": [
                {
                    "integration_id": "INT-CALLBACK-TEST",
                    "state": "published",
                    "provider_release_id": release_id,
                }
            ],
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        secret = Path(secret_file).read_bytes().strip()

        def headers(timestamp: str, body: bytes = raw) -> dict[str, str]:
            signature = hmac.new(
                secret, timestamp.encode() + b"." + body, hashlib.sha256
            ).hexdigest()
            return {
                "Content-Type": "application/json",
                "X-Postly-Timestamp": timestamp,
                "X-Postly-Callback-ID": str(callback_id),
                "X-Postly-Signature": f"sha256={signature}",
                "X-Correlation-ID": "COR-CALLBACK-TEST",
            }

        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 32000))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://middleware.test"
        ) as client:
            monkeypatch.setattr(settings, "postly_callback_enabled", False)
            disabled = await client.post(
                "/api/v1/social/provider-events",
                content=raw,
                headers=headers(str(int(time.time()))),
            )
            assert disabled.status_code == 404
            monkeypatch.setattr(settings, "postly_callback_enabled", True)
            timestamp = str(int(time.time()))
            crossover_payload = {
                **payload,
                "callback_id": str(uuid4()),
                "provider_results": [
                    {
                        "integration_id": "INT-OTHER",
                        "state": "published",
                        "provider_release_id": release_id,
                    }
                ],
            }
            crossover_raw = json.dumps(
                crossover_payload, separators=(",", ":")
            ).encode()
            crossover_signature = hmac.new(
                secret,
                timestamp.encode() + b"." + crossover_raw,
                hashlib.sha256,
            ).hexdigest()
            crossover = await client.post(
                "/api/v1/social/provider-events",
                content=crossover_raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Postly-Timestamp": timestamp,
                    "X-Postly-Callback-ID": crossover_payload["callback_id"],
                    "X-Postly-Signature": f"sha256={crossover_signature}",
                },
            )
            assert crossover.status_code == 409
            accepted = await client.post(
                "/api/v1/social/provider-events",
                content=raw,
                headers=headers(timestamp),
            )
            assert accepted.status_code == 202
            assert accepted.json()["persisted"] is True
            replay = await client.post(
                "/api/v1/social/provider-events",
                content=raw,
                headers=headers(timestamp),
            )
            assert replay.status_code == 409
            duplicate_payload = {**payload, "callback_id": str(uuid4()), "attempt": 2}
            duplicate_raw = json.dumps(
                duplicate_payload, separators=(",", ":")
            ).encode()
            duplicate_timestamp = str(int(time.time()))
            duplicate_signature = hmac.new(
                secret,
                duplicate_timestamp.encode() + b"." + duplicate_raw,
                hashlib.sha256,
            ).hexdigest()
            duplicate = await client.post(
                "/api/v1/social/provider-events",
                content=duplicate_raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Postly-Timestamp": duplicate_timestamp,
                    "X-Postly-Callback-ID": duplicate_payload["callback_id"],
                    "X-Postly-Signature": f"sha256={duplicate_signature}",
                },
            )
            assert duplicate.status_code == 202
            assert duplicate.json()["status"] == "duplicate_event"
            stale = await client.post(
                "/api/v1/social/provider-events",
                content=raw,
                headers=headers(str(int(time.time()) - 301)),
            )
            assert stale.status_code == 401
            changed = raw + b" "
            invalid_raw_signature = await client.post(
                "/api/v1/social/provider-events",
                content=changed,
                headers=headers(str(int(time.time())), raw),
            )
            assert invalid_raw_signature.status_code == 401
            metrics = await client.get("/metrics/")
            assert metrics.status_code == 200
            assert "codestra_social_callbacks_total" in metrics.text
            assert "private synthetic callback content" not in metrics.text
            assert release_id not in metrics.text

        async with factory() as session:
            callback_count = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM social_provider_callback WHERE event_id=:id"
                    ),
                    {"id": event_id},
                )
            ).scalar_one()
            audit = (
                await session.execute(
                    text("""
                    SELECT action,safe_details::text FROM social_audit_record a
                    JOIN social_content_job j ON j.id=a.job_id
                    WHERE j.content_job_id=:id ORDER BY sequence
                    """),
                    {"id": job_id},
                )
            ).all()
            assert callback_count == 1
            assert audit[-1][0] == "provider_callback_accepted"
            assert "private synthetic callback content" not in repr(audit)
    finally:
        app.dependency_overrides.pop(get_session, None)
        await engine.dispose()
