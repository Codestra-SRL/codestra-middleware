import hashlib
import hmac
import os
import time
from uuid import uuid4

import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.internal import ai_jobs as worker_api
from app.api.v1 import ai_console
from app.core import ai_jobs
from app.core.config import settings

SECRET = b"deterministic-test-only-qwen-worker-key-material"


def worker_headers(method: str, path: str, body: bytes, nonce: str | None = None):
    timestamp = str(int(time.time()))
    nonce = nonce or uuid4().hex
    scopes = "ai.auth ai.worker"
    canonical = "\n".join((method, path, "qwen-ai-01", timestamp, nonce, "3001",
        "spiffe://codestra.internal/service/qwen-ai-01", scopes,
        hashlib.sha256(body).hexdigest()))
    return {
        "X-Service-ID": "qwen-ai-01", "X-Timestamp": timestamp,
        "X-Nonce": nonce, "X-Signature": hmac.new(SECRET, canonical.encode(), hashlib.sha256).hexdigest(),
        "X-Client-Certificate-Serial": "3001",
        "X-Client-SPIFFE-ID": "spiffe://codestra.internal/service/qwen-ai-01",
        "X-Service-Scopes": scopes,
    }


def test_worker_identity_positive_negative_and_replay(tmp_path):
    secret = tmp_path / "hmac"
    secret.write_bytes(SECRET)
    settings.ai_hmac_secret_file = str(secret)
    settings.ai_worker_source_cidrs = "10.40.0.4/32"
    worker_api._nonces.clear()
    app = FastAPI()
    app.include_router(worker_api.router)
    client = TestClient(app, client=("10.40.0.4", 443))
    path = "/internal/api/v1/ai/auth/verify"
    headers = worker_headers("POST", path, b"")
    assert client.post(path, headers=headers).status_code == 200
    assert client.post(path, headers=headers).status_code == 409
    bad = worker_headers("POST", path, b"")
    bad["X-Client-Certificate-Serial"] = "9999"
    assert client.post(path, headers=bad).status_code == 403
    outside = TestClient(app, client=("10.40.0.5", 443))
    assert outside.post(path, headers=worker_headers("POST", path, b"")).status_code == 404


@pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="disposable PostgreSQL required")
@pytest.mark.asyncio
async def test_durable_job_lifecycle_tenant_stream_cancel_and_recovery():
    organization_id, workspace_id = uuid4(), uuid4()
    other_organization = uuid4()
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        await db.execute(text("""TRUNCATE ai_audit_events, ai_worker_heartbeats,
            ai_job_attempts, ai_job_chunks, ai_generation_jobs, ai_messages,
            ai_conversations CASCADE"""))
        await db.commit()
        conversation = await ai_jobs.create_conversation(
            db, organization_id, workspace_id, "synthetic-user", "Synthetic", "corr-create"
        )
        job = await ai_jobs.create_message_job(
            db, conversation_id=conversation["conversation_id"], organization_id=organization_id,
            workspace_id=workspace_id, user_id="synthetic-user", content="example.invalid prompt",
            task_type="chat", project_key=None, idempotency_key="fixture-key-0001",
            correlation_id="corr-job", max_attempts=2,
        )
        replay = await ai_jobs.create_message_job(
            db, conversation_id=conversation["conversation_id"], organization_id=organization_id,
            workspace_id=workspace_id, user_id="synthetic-user", content="example.invalid prompt",
            task_type="chat", project_key=None, idempotency_key="fixture-key-0001",
            correlation_id="corr-replay", max_attempts=2,
        )
        assert replay["job_id"] == job["job_id"] and replay["idempotent_replay"]
        claimed = await ai_jobs.claim(db, "synthetic-worker", 30, "corr-claim")
        assert claimed and claimed["id"] == job["job_id"]
        job_id = claimed["id"]
        assert await ai_jobs.append_chunk(db, job_id, "synthetic-worker",
            claimed["fencing_token"], 0, "synthetic output", 1024)
        assert not await ai_jobs.append_chunk(db, job_id, "synthetic-worker",
            claimed["fencing_token"], 0, "synthetic output", 1024)
        assert await ai_jobs.finish(db, job_id, "synthetic-worker", claimed["fencing_token"],
            failed=False, error_code=None, retryable=False, correlation_id="corr-complete") == "completed"
        with pytest.raises(PermissionError):
            await ai_jobs.heartbeat(db, job_id, "synthetic-worker", claimed["fencing_token"], 30)

        second = await ai_jobs.create_message_job(
            db, conversation_id=conversation["conversation_id"], organization_id=organization_id,
            workspace_id=workspace_id, user_id="synthetic-user", content="second synthetic prompt",
            task_type="chat", project_key=None, idempotency_key="fixture-key-0002",
            correlation_id="corr-second", max_attempts=1,
        )
        second_claim = await ai_jobs.claim(db, "synthetic-worker", 30, "corr-second-claim")
        await db.execute(text("UPDATE ai_generation_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=:id"),
                         {"id": second["job_id"]})
        await db.commit()
        recovered = await ai_jobs.recover_expired(db)
        assert recovered == {"retried": 0, "dead_lettered": 1}
        assert second_claim["attempt_count"] == 1

        third = await ai_jobs.create_message_job(
            db, conversation_id=conversation["conversation_id"], organization_id=organization_id,
            workspace_id=workspace_id, user_id="synthetic-user", content="cancel synthetic prompt",
            task_type="chat", project_key=None, idempotency_key="fixture-key-0003",
            correlation_id="corr-third", max_attempts=2,
        )

    app = FastAPI()
    app.include_router(ai_console.router)

    async def isolated_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[ai_console.get_session] = isolated_session
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )
    base_headers = {"Authorization": "Bearer synthetic", "X-Organization-ID": str(organization_id),
                    "X-Workspace-ID": str(workspace_id), "X-User-ID": "synthetic-user",
                    "X-Correlation-ID": "corr-cancel"}
    cancel = await client.post(f"/api/v1/ai/jobs/{third['job_id']}/cancel", headers=base_headers)
    assert cancel.status_code == 202 and cancel.json()["cancel_requested"]
    stream = await client.get(f"/api/v1/ai/jobs/{job_id}/stream", headers=base_headers)
    assert stream.status_code == 200
    assert "synthetic output" in stream.text and '"state": "completed"' in stream.text
    wrong_headers = {**base_headers, "X-Organization-ID": str(other_organization)}
    isolated = await client.get(f"/api/v1/ai/jobs/{job_id}/stream", headers=wrong_headers)
    assert '"code":"not_found"' in isolated.text
    await client.aclose()
    await engine.dispose()
