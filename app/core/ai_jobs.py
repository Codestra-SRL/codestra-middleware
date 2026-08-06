"""Transactional AI job repository with leases and fencing tokens."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def audit(
    db: AsyncSession, event_type: str, correlation_id: str, actor: str,
    *, organization_id: UUID | None = None, workspace_id: UUID | None = None,
    job_id: UUID | None = None, details: dict[str, Any] | None = None,
) -> None:
    await db.execute(text("""
        INSERT INTO ai_audit_events
          (id, organization_id, workspace_id, job_id, actor_fingerprint,
           event_type, correlation_id, safe_details)
        VALUES (:id, :org, :workspace, :job, :actor, :event, :correlation,
                CAST(:details AS jsonb))
    """), {"id": uuid4(), "org": organization_id, "workspace": workspace_id,
            "job": job_id, "actor": fingerprint(actor), "event": event_type,
            "correlation": correlation_id, "details": __import__("json").dumps(details or {})})


async def create_conversation(
    db: AsyncSession, organization_id: UUID, workspace_id: UUID,
    user_id: str, title: str, correlation_id: str,
) -> dict[str, Any]:
    conversation_id = uuid4()
    await db.execute(text("""
        INSERT INTO ai_conversations
          (id, organization_id, workspace_id, created_by, title)
        VALUES (:id, :org, :workspace, :user, :title)
    """), {"id": conversation_id, "org": organization_id,
            "workspace": workspace_id, "user": user_id, "title": title})
    await audit(db, "conversation.created", correlation_id, user_id,
                organization_id=organization_id, workspace_id=workspace_id,
                details={"conversation_id": str(conversation_id)})
    await db.commit()
    return {"conversation_id": conversation_id, "status": "active"}


async def create_message_job(
    db: AsyncSession, *, conversation_id: UUID, organization_id: UUID,
    workspace_id: UUID, user_id: str, content: str, task_type: str,
    project_key: str | None, idempotency_key: str, correlation_id: str,
    max_attempts: int,
) -> dict[str, Any]:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {
            "key": (
                f"ai-job:{organization_id}:{workspace_id}:"
                f"{idempotency_key}"
            )
        },
    )
    request_hash = hashlib.sha256(
        f"{conversation_id}\0{task_type}\0{project_key or ''}\0{content}".encode()
    ).hexdigest()
    existing = (await db.execute(text("""
        SELECT id, request_message_id, request_sha256, state
        FROM ai_generation_jobs
        WHERE organization_id=:org AND workspace_id=:workspace
          AND idempotency_key=:key
    """), {"org": organization_id, "workspace": workspace_id,
            "key": idempotency_key})).mappings().first()
    if existing:
        if existing["request_sha256"] != request_hash:
            raise ValueError("idempotency_conflict")
        return {"job_id": existing["id"], "message_id": existing["request_message_id"],
                "state": existing["state"], "idempotent_replay": True}
    owns = (await db.execute(text("""
        SELECT 1 FROM ai_conversations WHERE id=:conversation AND organization_id=:org
          AND workspace_id=:workspace AND status='active'
    """), {"conversation": conversation_id, "org": organization_id,
            "workspace": workspace_id})).scalar_one_or_none()
    if not owns:
        raise LookupError("conversation_not_found")
    message_id, job_id = uuid4(), uuid4()
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    await db.execute(text("""
        INSERT INTO ai_messages
          (id, conversation_id, organization_id, workspace_id, role, content, content_sha256)
        VALUES (:id, :conversation, :org, :workspace, 'user', :content, :hash)
    """), {"id": message_id, "conversation": conversation_id,
            "org": organization_id, "workspace": workspace_id,
            "content": content, "hash": content_hash})
    await db.execute(text("""
        INSERT INTO ai_generation_jobs
          (id, conversation_id, request_message_id, organization_id, workspace_id,
           requested_by, task_type, project_key, idempotency_key, request_sha256, max_attempts)
        VALUES (:id, :conversation, :message, :org, :workspace, :user, :task,
                :project, :key, :hash, :max_attempts)
    """), {"id": job_id, "conversation": conversation_id, "message": message_id,
            "org": organization_id, "workspace": workspace_id, "user": user_id,
            "task": task_type, "project": project_key, "key": idempotency_key,
            "hash": request_hash, "max_attempts": max_attempts})
    await audit(db, "job.queued", correlation_id, user_id,
                organization_id=organization_id, workspace_id=workspace_id,
                job_id=job_id, details={"task_type": task_type})
    await db.commit()
    return {"job_id": job_id, "message_id": message_id, "state": "queued",
            "idempotent_replay": False}


async def claim(db: AsyncSession, worker_id: str, lease_seconds: int,
                correlation_id: str) -> dict[str, Any] | None:
    row = (await db.execute(text("""
        WITH candidate AS (
          SELECT id FROM ai_generation_jobs
          WHERE state IN ('queued','retry_wait') AND next_attempt_at <= now()
            AND cancel_requested_at IS NULL
            AND (deadline_at IS NULL OR deadline_at > now())
          ORDER BY priority,created_at FOR UPDATE SKIP LOCKED LIMIT 1
        )
        UPDATE ai_generation_jobs j SET state='leased', lease_owner=:worker,
          lease_expires_at=now() + make_interval(secs => :lease_seconds),
          fencing_token=fencing_token+1, attempt_count=attempt_count+1, updated_at=now()
        FROM candidate WHERE j.id=candidate.id
        RETURNING j.*
    """), {"worker": worker_id, "lease_seconds": lease_seconds})).mappings().first()
    if not row:
        await db.commit()
        return None
    await db.execute(text("""
        INSERT INTO ai_job_attempts
          (id, job_id, attempt_number, fencing_token, worker_id, state)
        VALUES (:id,:job,:attempt,:token,:worker,'leased')
    """), {"id": uuid4(), "job": row["id"], "attempt": row["attempt_count"],
            "token": row["fencing_token"], "worker": worker_id})
    await audit(db, "job.claimed", correlation_id, worker_id,
                organization_id=row["organization_id"], workspace_id=row["workspace_id"],
                job_id=row["id"], details={"attempt": row["attempt_count"],
                                            "fencing_token": row["fencing_token"]})
    await db.commit()
    allowed = ("id", "conversation_id", "organization_id", "workspace_id",
               "task_type", "command_type", "schema_version", "project_key",
               "attempt_count", "fencing_token", "lease_expires_at", "deadline_at",
               "command_payload", "model_profile", "resource_limits",
               "data_classification", "approval_policy")
    return {key: row[key] for key in allowed}


async def assert_lease(db: AsyncSession, job_id: UUID, worker_id: str,
                       fencing_token: int) -> dict[str, Any]:
    row = (await db.execute(text("""
        SELECT * FROM ai_generation_jobs WHERE id=:job AND state='leased'
          AND lease_owner=:worker AND fencing_token=:token AND lease_expires_at > now()
        FOR UPDATE
    """), {"job": job_id, "worker": worker_id,
            "token": fencing_token})).mappings().first()
    if not row:
        raise PermissionError("stale_or_invalid_lease")
    return dict(row)


async def heartbeat(db: AsyncSession, job_id: UUID, worker_id: str,
                    fencing_token: int, lease_seconds: int, *, service_id: str,
                    certificate_serial: str, spiffe_id: str) -> datetime:
    await assert_lease(db, job_id, worker_id, fencing_token)
    expires = datetime.now(timezone.utc)
    row = (await db.execute(text("""
        UPDATE ai_generation_jobs SET lease_expires_at=now()+make_interval(secs=>:seconds),
          updated_at=now() WHERE id=:job RETURNING lease_expires_at
    """), {"seconds": lease_seconds, "job": job_id})).mappings().one()
    await db.execute(text("""
        INSERT INTO ai_worker_heartbeats(worker_id,service_id,certificate_serial,spiffe_id,last_seen_at,current_job_id)
        VALUES (:worker,:service,:serial,:spiffe,now(),:job)
        ON CONFLICT(worker_id) DO UPDATE SET service_id=:service,
          certificate_serial=:serial,spiffe_id=:spiffe,last_seen_at=now(),
          current_job_id=:job
    """), {"worker": worker_id, "service": service_id,
            "serial": certificate_serial, "spiffe": spiffe_id, "job": job_id})
    await db.commit()
    return row["lease_expires_at"] or expires


async def append_chunk(db: AsyncSession, job_id: UUID, worker_id: str,
                       fencing_token: int, sequence: int, content: str,
                       max_output_bytes: int) -> bool:
    row = await assert_lease(db, job_id, worker_id, fencing_token)
    size = len(content.encode())
    if row["output_bytes"] + size > max_output_bytes:
        raise OverflowError("output_limit_exceeded")
    result = await db.execute(text("""
        INSERT INTO ai_job_chunks(id,job_id,organization_id,workspace_id,sequence,
          fencing_token,content,content_sha256)
        VALUES (:id,:job,:org,:workspace,:sequence,:token,:content,:hash)
        ON CONFLICT(job_id,sequence) DO NOTHING
    """), {"id": uuid4(), "job": job_id, "org": row["organization_id"],
            "workspace": row["workspace_id"], "sequence": sequence,
            "token": fencing_token, "content": content,
            "hash": hashlib.sha256(content.encode()).hexdigest()})
    inserted = int(getattr(result, "rowcount", 0)) == 1
    if inserted:
        await db.execute(text("UPDATE ai_generation_jobs SET output_bytes=output_bytes+:size,updated_at=now() WHERE id=:job"),
                         {"size": size, "job": job_id})
    await db.commit()
    return inserted


async def finish(db: AsyncSession, job_id: UUID, worker_id: str,
                 fencing_token: int, *, failed: bool, error_code: str | None,
                 retryable: bool, correlation_id: str,
                 completion_state: str = "completed") -> str:
    row = await assert_lease(db, job_id, worker_id, fencing_token)
    if row["cancel_requested_at"] is not None:
        state = "cancelled"
    elif not failed:
        state = completion_state
    elif retryable and row["attempt_count"] < row["max_attempts"]:
        state = "retry_wait"
    elif failed:
        state = "dead_letter"
    else:
        state = "failed"
    delay = min(300, 2 ** min(row["attempt_count"], 8))
    await db.execute(text("""
        UPDATE ai_generation_jobs SET state=:state, lease_owner=NULL, lease_expires_at=NULL,
          next_attempt_at=CASE WHEN :state='retry_wait' THEN now()+make_interval(secs=>:delay) ELSE next_attempt_at END,
          failure_code=:error, completed_at=CASE WHEN :state IN ('completed','approval_required','cancelled','dead_letter','failed') THEN now() END,
          updated_at=now() WHERE id=:job
    """), {"state": state, "delay": delay, "error": error_code, "job": job_id})
    await db.execute(text("""
        UPDATE ai_job_attempts SET state=:state,safe_error_code=:error,finished_at=now()
        WHERE job_id=:job AND fencing_token=:token
    """), {"state": state, "error": error_code, "job": job_id, "token": fencing_token})
    if state == "dead_letter":
        await db.execute(text("""INSERT INTO ai_job_dead_letters
          (job_id,organization_id,workspace_id,safe_error_code,attempt_count,payload_sha256)
          VALUES(:job,:org,:workspace,:error,:attempts,:hash)
          ON CONFLICT(job_id) DO NOTHING"""),
          {"job": job_id, "org": row["organization_id"], "workspace": row["workspace_id"],
           "error": error_code or "attempts_exhausted", "attempts": row["attempt_count"],
           "hash": row["request_sha256"]})
    await audit(db, f"job.{state}", correlation_id, worker_id,
                organization_id=row["organization_id"], workspace_id=row["workspace_id"],
                job_id=job_id, details={"safe_error_code": error_code or ""})
    await db.commit()
    return state


async def recover_expired(db: AsyncSession) -> dict[str, int]:
    retried_result = await db.execute(text("""
        UPDATE ai_generation_jobs SET state='retry_wait',lease_owner=NULL,lease_expires_at=NULL,
          next_attempt_at=now(),updated_at=now()
        WHERE state='leased' AND lease_expires_at <= now() AND attempt_count < max_attempts
          AND (deadline_at IS NULL OR deadline_at > now())
    """))
    retried = int(getattr(retried_result, "rowcount", 0))
    dead_result = await db.execute(text("""
        UPDATE ai_generation_jobs SET state='dead_letter',lease_owner=NULL,lease_expires_at=NULL,
          failure_code='lease_expired',completed_at=now(),updated_at=now()
        WHERE state='leased' AND lease_expires_at <= now() AND attempt_count >= max_attempts
          AND (deadline_at IS NULL OR deadline_at > now())
    """))
    dead = int(getattr(dead_result, "rowcount", 0))
    if dead:
        await db.execute(text("""INSERT INTO ai_job_dead_letters
          (job_id,organization_id,workspace_id,safe_error_code,attempt_count,payload_sha256)
          SELECT id,organization_id,workspace_id,'lease_expired',attempt_count,request_sha256
          FROM ai_generation_jobs WHERE state='dead_letter' AND failure_code='lease_expired'
          ON CONFLICT(job_id) DO NOTHING"""))
    await db.commit()
    return {"retried": retried, "dead_lettered": dead}


async def expire_deadlines(db: AsyncSession) -> int:
    result = await db.execute(text("""
        UPDATE ai_generation_jobs SET state='expired',lease_owner=NULL,lease_expires_at=NULL,
          failure_code='deadline_expired',completed_at=now(),updated_at=now()
        WHERE state IN ('queued','retry_wait','leased') AND deadline_at <= now()
    """))
    await db.commit()
    return int(getattr(result, "rowcount", 0))
