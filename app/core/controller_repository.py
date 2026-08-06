"""Transactional PostgreSQL repository for the restricted Controller."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automation import canonical_hash, redact
from app.core.controller import ControllerError


class PostgresControllerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_task(self, body: dict[str, Any], *, tenant_id: str,
                          request_id: str, correlation_id: str,
                          idempotency_key: str) -> tuple[dict[str, Any], bool]:
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        request_hash = canonical_hash(body)
        task_id = uuid4()
        try:
            row = (await self.session.execute(text("""
                INSERT INTO controller_tasks
                (id,tenant_id,workspace,title,objective,request_id,correlation_id,
                 idempotency_key_hash,request_hash)
                VALUES (:id,:tenant,:workspace,:title,:objective,:request,:correlation,:key_hash,:request_hash)
                ON CONFLICT (tenant_id,idempotency_key_hash) DO NOTHING
                RETURNING *
            """), {"id": task_id, "tenant": tenant_id, "workspace": body["workspace"],
                    "title": body["title"], "objective": body["objective"],
                    "request": request_id, "correlation": correlation_id,
                    "key_hash": key_hash, "request_hash": request_hash})).mappings().first()
            if row is None:
                prior = (await self.session.execute(text("""
                    SELECT * FROM controller_tasks
                    WHERE tenant_id=:tenant AND idempotency_key_hash=:key_hash
                """), {"tenant": tenant_id, "key_hash": key_hash})).mappings().one()
                if prior["request_hash"] != request_hash:
                    raise ControllerError("idempotency key conflict")
                await self.session.commit()
                return dict(prior), True
            await self.append_audit(task_id, tenant_id, "task.created", {"request_id": request_id})
            await self.session.commit()
            return dict(row), False
        except Exception:
            await self.session.rollback()
            raise

    async def append_audit(self, task_id: UUID, tenant_id: str, action: str,
                           details: dict[str, Any]) -> dict[str, Any]:
        task = (await self.session.execute(text("""
            SELECT id,correlation_id FROM controller_tasks
            WHERE id=:id AND tenant_id=:tenant FOR UPDATE
        """), {"id": task_id, "tenant": tenant_id})).mappings().first()
        if task is None:
            raise ControllerError("task not found")
        prior = (await self.session.execute(text("""
            SELECT sequence,record_hash FROM controller_task_audit
            WHERE task_id=:id ORDER BY sequence DESC LIMIT 1
        """), {"id": task_id})).mappings().first()
        sequence = int(prior["sequence"]) + 1 if prior else 1
        previous_hash = str(prior["record_hash"]) if prior else "0" * 64
        safe = redact(details)
        material = {"sequence": sequence, "task_id": str(task_id), "tenant_id": tenant_id,
                    "action": action, "details": safe, "previous_hash": previous_hash,
                    "correlation_id": task["correlation_id"]}
        record_hash = canonical_hash(material)
        await self.session.execute(text("""
            INSERT INTO controller_task_audit
            (task_id,tenant_id,sequence,action,safe_details,previous_hash,record_hash,correlation_id)
            VALUES (:id,:tenant,:sequence,:action,CAST(:details AS jsonb),:previous,:record,:correlation)
        """), {"id": task_id, "tenant": tenant_id, "sequence": sequence,
                "action": action, "details": json.dumps(safe), "previous": previous_hash,
                "record": record_hash, "correlation": task["correlation_id"]})
        return {**material, "record_hash": record_hash}

    async def claim(self, server_id: str, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
        expires = datetime.now(timezone.utc) + timedelta(seconds=min(max(lease_seconds, 10), 300))
        row = (await self.session.execute(text("""
            WITH candidate AS (
              SELECT id FROM controller_tasks
              WHERE state='QUEUED' AND available_at<=now()
              ORDER BY priority DESC,available_at,created_at
              FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE controller_tasks t SET state='RUNNING',lease_owner=:owner,
              lease_expires_at=:expires,heartbeat_at=now(),attempt_count=attempt_count+1,
              version=version+1,updated_at=now()
            FROM candidate WHERE t.id=candidate.id RETURNING t.*
        """), {"owner": f"{server_id}:{worker_id}", "expires": expires})).mappings().first()
        if row:
            await self.append_audit(row["id"], row["tenant_id"], "task.claimed",
                                    {"worker_hash": hashlib.sha256(worker_id.encode()).hexdigest()})
        await self.session.commit()
        return dict(row) if row else None

    async def heartbeat(self, task_id: UUID, tenant_id: str, worker: str,
                        expected_version: int, lease_seconds: int) -> dict[str, Any]:
        row = (await self.session.execute(text("""
            UPDATE controller_tasks SET heartbeat_at=now(),
              lease_expires_at=now()+(:seconds * interval '1 second'),version=version+1,updated_at=now()
            WHERE id=:id AND tenant_id=:tenant AND state='RUNNING'
              AND lease_owner=:worker AND version=:version AND lease_expires_at>now()
            RETURNING *
        """), {"id": task_id, "tenant": tenant_id, "worker": worker,
                "version": expected_version, "seconds": min(max(lease_seconds, 10), 300)})).mappings().first()
        if row is None:
            await self.session.rollback()
            raise ControllerError("lease or version denied")
        await self.session.commit()
        return dict(row)

    async def recover_expired(self) -> dict[str, int]:
        rows = (await self.session.execute(text("""
            UPDATE controller_tasks SET
              state=CASE WHEN attempt_count<max_attempts THEN 'QUEUED' ELSE 'DEAD_LETTER' END,
              available_at=CASE WHEN attempt_count<max_attempts
                THEN now()+(LEAST(300,power(2,attempt_count)) * interval '1 second') ELSE available_at END,
              lease_owner=NULL,lease_expires_at=NULL,version=version+1,updated_at=now()
            WHERE state='RUNNING' AND lease_expires_at<=now()
            RETURNING id,tenant_id,state
        """))).mappings().all()
        for row in rows:
            await self.append_audit(row["id"], row["tenant_id"], "task.lease_recovered",
                                    {"state": row["state"]})
        await self.session.commit()
        return {"retried": sum(row["state"] == "QUEUED" for row in rows),
                "dead_lettered": sum(row["state"] == "DEAD_LETTER" for row in rows)}

    async def consume_approval(self, jti: str, task_id: UUID, tenant_id: str) -> None:
        digest = hashlib.sha256(jti.encode()).hexdigest()
        row = await self.session.execute(text("""
            UPDATE controller_approvals SET consumed_at=now(),state='CONSUMED'
            WHERE task_id=:task AND tenant_id=:tenant AND token_jti_hash=:digest
              AND state='APPROVED' AND consumed_at IS NULL AND token_expires_at>now()
            RETURNING id
        """), {"task": task_id, "tenant": tenant_id, "digest": digest})
        if row.first() is None:
            await self.session.rollback()
            raise ControllerError("approval token replay or expiry rejected")
        await self.session.commit()

    async def save_approval(self, *, task_id: UUID, tenant_id: str, plan_hash: str,
                            server_id: str, tools: list[str], approver: str,
                            jti: str, expires_at: datetime) -> UUID:
        approval_id = uuid4()
        await self.session.execute(text("""
            INSERT INTO controller_approvals
            (id,task_id,tenant_id,plan_hash,server_id,tools,approver_fingerprint,
             token_jti_hash,token_expires_at)
            VALUES (:id,:task,:tenant,:plan,:server,CAST(:tools AS jsonb),:approver,:jti,:expires)
        """), {"id": approval_id, "task": task_id, "tenant": tenant_id,
                "plan": plan_hash, "server": server_id, "tools": json.dumps(tools),
                "approver": hashlib.sha256(approver.encode()).hexdigest(),
                "jti": hashlib.sha256(jti.encode()).hexdigest(), "expires": expires_at})
        await self.session.commit()
        return approval_id

    async def save_verification(self, record: dict[str, Any]) -> None:
        try:
            await self.session.execute(text("""
                INSERT INTO controller_verifications
                (verification_code,task_id,execution_id,tenant_id,checks,evidence_hash,signature)
                VALUES (:code,:task,:execution,:tenant,CAST(:checks AS jsonb),:evidence,:signature)
            """), {"code": record["verification_code"], "task": record["task_id"],
                    "execution": record["execution_id"], "tenant": record["tenant_id"],
                    "checks": json.dumps(record["checks"]), "evidence": record["evidence_hash"],
                    "signature": record["signature"]})
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ControllerError("verification conflict") from exc
