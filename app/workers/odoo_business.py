"""Atomic claim, retry, completion, and reconciliation operations for Wave 3."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def claim_commands(
    db: AsyncSession, *, worker_id: str, limit: int = 25, lease_seconds: int = 60,
    delivery_enabled: bool = False,
) -> list[dict[str, object]]:
    if not delivery_enabled:
        return []
    rows = (await db.execute(text("""
        WITH candidates AS (
            SELECT id FROM odoo_business_command
            WHERE delivery_mode <> 'DISABLED'
              AND approval_state IN ('NOT_REQUIRED','APPROVED')
              AND (state IN ('READY','RETRY_WAIT') OR
                   (state='LEASED' AND lease_expires_at < now()))
              AND next_attempt_at <= now() AND cancel_requested_at IS NULL
            ORDER BY next_attempt_at, created_at, id
            FOR UPDATE SKIP LOCKED LIMIT :limit
        )
        UPDATE odoo_business_command command
        SET state='LEASED', lease_owner=:worker,
            lease_expires_at=now()+make_interval(secs => :lease_seconds),
            attempt_count=attempt_count+1, fencing_token=fencing_token+1,
            updated_by=:worker
        FROM candidates WHERE command.id=candidates.id
        RETURNING command.id, command.tenant_id, command.workspace_id,
                  command.resource_type, command.operation, command.resource_key,
                  command.payload, command.expected_version, command.attempt_count,
                  command.max_attempts, command.fencing_token
    """), {"worker": worker_id, "limit": min(max(limit, 1), 100),
             "lease_seconds": min(max(lease_seconds, 5), 300)})).mappings().all()
    await db.commit()
    return [dict(row) for row in rows]


async def complete_command(
    db: AsyncSession, command_id: UUID, worker_id: str, fencing_token: int,
    *, remote_model: str, remote_id: int, remote_version: str | None,
) -> bool:
    result = await db.execute(text("""
        WITH completed AS (
            UPDATE odoo_business_command SET state='SUCCEEDED', lease_owner=NULL,
                lease_expires_at=NULL, updated_by=:worker
            WHERE id=:id AND state='LEASED' AND lease_owner=:worker
              AND fencing_token=:fencing RETURNING *
        ), reference AS (
            INSERT INTO odoo_business_reference (
                tenant_id,workspace_id,resource_type,resource_key,odoo_model,
                odoo_record_id,remote_version,created_by,updated_by
            ) SELECT tenant_id,workspace_id,resource_type,resource_key,:model,
                     :remote_id,:remote_version,:worker,:worker FROM completed
            ON CONFLICT (tenant_id,workspace_id,resource_type,resource_key)
            DO UPDATE SET odoo_model=EXCLUDED.odoo_model,
                          odoo_record_id=EXCLUDED.odoo_record_id,
                          remote_version=EXCLUDED.remote_version,
                          status='ACTIVE',updated_by=:worker
            RETURNING id
        )
        INSERT INTO odoo_business_audit (
            tenant_id,workspace_id,command_id,reference_id,action,actor,correlation_id,metadata
        ) SELECT completed.tenant_id,completed.workspace_id,completed.id,reference.id,
                 'DELIVERY_SUCCEEDED',:worker,completed.correlation_id,
                 jsonb_build_object('resource_type',completed.resource_type)
          FROM completed CROSS JOIN reference RETURNING command_id
    """), {"id": command_id, "worker": worker_id, "fencing": fencing_token,
             "model": remote_model[:96], "remote_id": remote_id,
             "remote_version": remote_version[:128] if remote_version else None})
    await db.commit()
    return result.scalar_one_or_none() is not None


async def fail_command(
    db: AsyncSession, command_id: UUID, worker_id: str, fencing_token: int,
    error_code: str, *, retryable: bool,
) -> str | None:
    state = (await db.execute(text("""
        UPDATE odoo_business_command
        SET state=CASE
              WHEN NOT :retryable OR attempt_count >= max_attempts THEN 'DEAD_LETTER'
              ELSE 'RETRY_WAIT' END,
            next_attempt_at=CASE WHEN :retryable AND attempt_count < max_attempts
              THEN now()+make_interval(secs => LEAST(300, (2 ^ attempt_count)::integer))
              ELSE next_attempt_at END,
            lease_owner=NULL,lease_expires_at=NULL,last_error_code=:error,
            updated_by=:worker
        WHERE id=:id AND state='LEASED' AND lease_owner=:worker
          AND fencing_token=:fencing RETURNING state
    """), {"id": command_id, "worker": worker_id, "fencing": fencing_token,
             "error": error_code[:64], "retryable": retryable})).scalar_one_or_none()
    if state is not None:
        await db.execute(text("""
            INSERT INTO odoo_business_audit
              (tenant_id,workspace_id,command_id,action,actor,correlation_id,metadata)
            SELECT tenant_id,workspace_id,id,'DELIVERY_FAILED',:worker,correlation_id,
                   jsonb_build_object('state',CAST(:state AS text),
                                      'error_code',CAST(:error AS text))
            FROM odoo_business_command WHERE id=:id
        """), {"id": command_id, "worker": worker_id, "state": state,
                 "error": error_code[:64]})
    await db.commit()
    return state


async def recover_expired_leases(db: AsyncSession) -> dict[str, int]:
    result = await db.execute(text("""
        UPDATE odoo_business_command
        SET state=CASE WHEN attempt_count >= max_attempts THEN 'DEAD_LETTER' ELSE 'RETRY_WAIT' END,
            lease_owner=NULL,lease_expires_at=NULL,last_error_code='LEASE_EXPIRED',
            next_attempt_at=now(),updated_by='lease-recovery'
        WHERE state='LEASED' AND lease_expires_at < now()
        RETURNING state
    """))
    states = list(result.scalars())
    await db.commit()
    return {"retried": states.count("RETRY_WAIT"), "dead_lettered": states.count("DEAD_LETTER")}


async def claim_reconciliation(
    db: AsyncSession, *, worker_id: str, limit: int = 25, lease_seconds: int = 60
) -> list[dict[str, object]]:
    rows = (await db.execute(text("""
        WITH candidates AS (
            SELECT id FROM odoo_business_reconciliation
            WHERE (state IN ('PENDING','RETRY_WAIT') OR
                   (state='LEASED' AND lease_expires_at < now()))
              AND next_attempt_at <= now()
            ORDER BY next_attempt_at,id FOR UPDATE SKIP LOCKED LIMIT :limit
        )
        UPDATE odoo_business_reconciliation item
        SET state='LEASED',lease_owner=:worker,
            lease_expires_at=now()+make_interval(secs => :lease_seconds),
            attempt_count=attempt_count+1,fencing_token=fencing_token+1,
            updated_by=:worker
        FROM candidates WHERE item.id=candidates.id RETURNING item.*
    """), {"worker": worker_id, "limit": min(max(limit, 1), 100),
             "lease_seconds": min(max(lease_seconds, 5), 300)})).mappings().all()
    await db.commit()
    return [dict(row) for row in rows]
