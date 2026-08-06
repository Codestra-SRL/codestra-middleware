from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.internal import ai_jobs as worker_api
from app.core import ai_jobs, ai_orchestration
from app.core.ai_contracts import AIResult
from tests.test_ai_orchestration_db import make_command


def test_exact_private_queue_route_and_auth_contract() -> None:
    paths = {
        (route.path, method)
        for route in worker_api.router.routes
        for method in (route.methods or set())
    }
    expected = {
        ("/internal/api/v1/ai/worker/jobs/claim", "POST"),
        ("/internal/api/v1/ai/worker/jobs/{job_id}/heartbeat", "POST"),
        ("/internal/api/v1/ai/worker/jobs/{job_id}/complete", "POST"),
        ("/internal/api/v1/ai/worker/jobs/{job_id}/fail", "POST"),
        ("/internal/api/v1/ai/worker/jobs/{job_id}/cancel", "POST"),
        ("/internal/api/v1/ai/worker/jobs/{job_id}", "GET"),
        ("/internal/api/v1/ai/worker/dead-letters", "GET"),
        ("/internal/api/v1/ai/worker/dead-letters/{job_id}/retry", "POST"),
    }
    assert expected <= paths
    source = Path(worker_api.__file__).read_text()
    for required in (
        'signature_version != "v2"',
        "canonical_signing_string_v2(",
        "X-Tenant-ID",
        "X-Workspace-ID",
        "ai_service_nonces",
        "settings.ai_worker_id",
        "FOR UPDATE SKIP LOCKED",
    ):
        if required == "FOR UPDATE SKIP LOCKED":
            assert required in Path(ai_jobs.__file__).read_text()
        else:
            assert required in source


@pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="disposable PostgreSQL required"
)
@pytest.mark.asyncio
async def test_dead_letter_evidence_duplicate_result_and_approved_manual_retry() -> (
    None
):
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tenant, workspace = uuid4(), uuid4()
    try:
        async with sessions() as db:
            await db.execute(
                text("""TRUNCATE ai_job_results,ai_job_events,ai_job_dead_letters,
              ai_job_approvals,ai_usage_ledger,ai_worker_registrations,ai_audit_events,
              ai_worker_heartbeats,ai_job_attempts,ai_job_chunks,ai_generation_jobs,
              ai_messages,ai_conversations,ai_service_nonces,ai_tenant_quotas CASCADE""")
            )
            await db.commit()

            command = make_command(tenant=tenant)
            command.resource_limits.retry_count = 0
            await ai_orchestration.submit(db, command, workspace)
            claimed = await ai_jobs.claim(
                db,
                "qwen-ai-01-worker",
                30,
                "corr-dead-letter",
                organization_id=tenant,
                workspace_id=workspace,
            )
            assert claimed is not None
            state = await ai_jobs.finish(
                db,
                command.command_id,
                "qwen-ai-01-worker",
                claimed["fencing_token"],
                failed=True,
                error_code="model_timeout",
                retryable=True,
                correlation_id="corr-dead-letter",
                safe_error_details={
                    "component": "litellm",
                    "secret_token": "must-redact",
                },
            )
            assert state == "dead_letter"
            dead = (
                (
                    await db.execute(
                        text("""SELECT * FROM ai_job_dead_letters
              WHERE job_id=:job AND tenant_id=:tenant AND workspace_id=:workspace"""),
                        {
                            "job": command.command_id,
                            "tenant": tenant,
                            "workspace": workspace,
                        },
                    )
                )
                .mappings()
                .one()
            )
            assert dead["final_error_code"] == "model_timeout"
            assert dead["attempt_count"] == dead["max_attempts"] == 1
            assert dead["safe_error_details"] == {"component": "litellm"}
            assert dead["manual_retry_requires_new_approval"] is True
            assert len(dead["evidence_hash"]) == 64
            with pytest.raises(PermissionError, match="new_approval_required"):
                await ai_jobs.retry_dead_letter(
                    db,
                    command.command_id,
                    uuid4(),
                    tenant,
                    workspace,
                    "qwen-ai-01-worker",
                    "corr-denied-retry",
                )

            approval_id = uuid4()
            await db.execute(
                text("""INSERT INTO ai_job_approvals
              (id,job_id,organization_id,workspace_id,action_type,proposal,
               proposal_sha256,state,requested_by,decided_by_fingerprint,
               decision_reason,decided_at)
              VALUES(:id,:job,:tenant,:workspace,'dead_letter.retry','{}'::jsonb,
               :hash,'approved','operator',:actor,'bounded retry',now())"""),
                {
                    "id": approval_id,
                    "job": command.command_id,
                    "tenant": tenant,
                    "workspace": workspace,
                    "hash": hashlib.sha256(b"{}").hexdigest(),
                    "actor": hashlib.sha256(b"approver").hexdigest(),
                },
            )
            await db.commit()
            assert await ai_jobs.retry_dead_letter(
                db,
                command.command_id,
                approval_id,
                tenant,
                workspace,
                "qwen-ai-01-worker",
                "corr-approved-retry",
            ) == {"state": "retry_wait"}
            await db.execute(
                text("""UPDATE ai_generation_jobs SET state='cancelled'
              WHERE id=:job"""),
                {"job": command.command_id},
            )
            await db.commit()

            result_command = make_command(tenant=tenant)
            await ai_orchestration.submit(db, result_command, workspace)
            result_claim = await ai_jobs.claim(
                db,
                "qwen-ai-01-worker",
                30,
                "corr-result",
                organization_id=tenant,
                workspace_id=workspace,
            )
            now = datetime.now(timezone.utc)
            result = AIResult.model_validate(
                {
                    "command_id": result_command.command_id,
                    "job_id": result_command.command_id,
                    "status": "SUCCEEDED",
                    "result_schema_version": "1.0",
                    "model_used": "fixture",
                    "provider_used": "mock",
                    "started_at": now,
                    "completed_at": now,
                    "latency_ms": 1,
                    "token_usage": {},
                    "resource_usage": {},
                    "output": {"proposal": "safe"},
                    "structured_artifacts": [],
                    "warnings": [],
                    "policy_decisions": [],
                    "error": None,
                    "retryability": "none",
                    "audit_reference": "audit-fixture",
                }
            )
            completion_state = await ai_orchestration.store_result(
                db, dict(result_claim), result
            )
            await ai_jobs.finish(
                db,
                result_command.command_id,
                "qwen-ai-01-worker",
                result_claim["fencing_token"],
                failed=False,
                error_code=None,
                retryable=False,
                correlation_id="corr-result",
                completion_state=completion_state,
            )
            assert await ai_jobs.completed_result_status(
                db, result_command.command_id, tenant, workspace, result
            ) == {"state": "completed", "duplicate": "true"}
            changed = result.model_copy(update={"output": {"proposal": "different"}})
            with pytest.raises(PermissionError, match="duplicate_result_rejected"):
                await ai_jobs.completed_result_status(
                    db, result_command.command_id, tenant, workspace, changed
                )
    finally:
        await engine.dispose()
