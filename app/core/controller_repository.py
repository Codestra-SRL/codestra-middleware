"""Transactional PostgreSQL repository for the restricted Controller."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.automation import canonical_hash, redact
from app.core.controller import AGENT_TOOL_POLICIES, ApprovalTokens, ControllerError, _reject_forbidden


class ControllerRepository(Protocol):
    """Runtime persistence boundary implemented by durable and test backends."""

    tokens: ApprovalTokens

    def create_task(self, *args: Any, **kwargs: Any) -> Any: ...
    def get_task(self, *args: Any, **kwargs: Any) -> Any: ...
    def plan(self, *args: Any, **kwargs: Any) -> Any: ...
    def approve(self, *args: Any, **kwargs: Any) -> Any: ...
    def queue(self, *args: Any, **kwargs: Any) -> Any: ...
    def claim(self, *args: Any, **kwargs: Any) -> Any: ...
    def heartbeat(self, *args: Any, **kwargs: Any) -> Any: ...
    def finish(self, *args: Any, **kwargs: Any) -> Any: ...
    def fail(self, *args: Any, **kwargs: Any) -> Any: ...
    def recover_expired(self, *args: Any, **kwargs: Any) -> Any: ...


class PostgresControllerRepository:
    def __init__(self, session: AsyncSession, tokens: ApprovalTokens | None = None):
        self.session = session
        self.tokens = tokens

    @staticmethod
    def public(row: dict[str, Any]) -> dict[str, Any]:
        return {key: row.get(key) for key in (
            "id", "tenant_id", "workspace", "title", "objective", "request_id",
            "correlation_id", "state", "plan", "plan_hash", "priority", "attempt_count",
            "max_attempts", "available_at", "lease_expires_at", "version",
        )} | {"task_id": str(row["id"])}

    async def get_task(self, task_id: UUID, tenant_id: str, *, lock: bool = False) -> dict[str, Any]:
        suffix = " FOR UPDATE" if lock else ""
        row = (await self.session.execute(text(
            "SELECT * FROM controller_tasks WHERE id=:id AND tenant_id=:tenant" + suffix
        ), {"id": task_id, "tenant": tenant_id})).mappings().first()
        if row is None:
            raise ControllerError("task not found")
        return dict(row)

    async def plan(self, task_id: UUID, tenant_id: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        for step in steps:
            if not any(step.get("tool") in tools for tools in AGENT_TOOL_POLICIES.values()):
                raise ControllerError("unknown tool")
            _reject_forbidden(step.get("arguments", {}))
        plan_hash = canonical_hash(steps)
        row = (await self.session.execute(text("""
          UPDATE controller_tasks SET state='AWAITING_APPROVAL',plan=CAST(:plan AS jsonb),
            plan_hash=:hash,version=version+1,updated_at=now()
          WHERE id=:id AND tenant_id=:tenant AND state='CREATED' RETURNING *
        """), {"id": task_id, "tenant": tenant_id, "plan": json.dumps(steps),
                "hash": plan_hash})).mappings().first()
        if row is None:
            raise ControllerError("invalid task state transition")
        await self.append_audit(task_id, tenant_id, "task.plan_ready", {"plan_hash": plan_hash})
        await self.session.commit()
        return dict(row)

    async def approve(self, task_id: UUID, tenant_id: str, plan_hash: str,
                      approver: str, server_id: str) -> tuple[dict[str, Any], str]:
        if self.tokens is None:
            raise ControllerError("approval signing key is unavailable")
        task = await self.get_task(task_id, tenant_id, lock=True)
        if task["state"] != "AWAITING_APPROVAL" or task["plan_hash"] != plan_hash:
            raise ControllerError("approval does not match current plan")
        tools = sorted({step["tool"] for step in task["plan"]})
        if server_id not in AGENT_TOOL_POLICIES or any(tool not in AGENT_TOOL_POLICIES[server_id] for tool in tools):
            raise ControllerError("server tool scope denied")
        token = self.tokens.issue({"task_id": str(task_id), "tenant_id": tenant_id,
            "server_id": server_id, "workspace": task["workspace"], "tools": tools,
            "plan_hash": plan_hash, "approver_hash": hashlib.sha256(approver.encode()).hexdigest()})
        encoded = token.split(".")[0]
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        await self.save_approval(task_id=task_id, tenant_id=tenant_id, plan_hash=plan_hash,
            server_id=server_id, tools=tools, approver=approver, jti=payload["jti"],
            expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc), commit=False)
        row = (await self.session.execute(text("""UPDATE controller_tasks SET state='APPROVED',
          version=version+1,updated_at=now() WHERE id=:id AND tenant_id=:tenant RETURNING *"""),
          {"id": task_id, "tenant": tenant_id})).mappings().one()
        await self.append_audit(task_id, tenant_id, "task.approved", {"server_id": server_id})
        await self.session.commit()
        return dict(row), token

    async def transition(self, task_id: UUID, tenant_id: str, states: tuple[str, ...],
                         target: str, action: str) -> dict[str, Any]:
        row = (await self.session.execute(text("""UPDATE controller_tasks SET state=:target,
          version=version+1,updated_at=now() WHERE id=:id AND tenant_id=:tenant
          AND state=ANY(:states) RETURNING *"""), {"target": target, "id": task_id,
          "tenant": tenant_id, "states": list(states)})).mappings().first()
        if row is None:
            raise ControllerError("invalid task state transition")
        await self.append_audit(task_id, tenant_id, action, {})
        await self.session.commit()
        return dict(row)

    async def queue(self, task_id: UUID, tenant_id: str, priority: int,
                    timeout_seconds: int, max_attempts: int) -> dict[str, Any]:
        row = (await self.session.execute(text("""UPDATE controller_tasks SET state='QUEUED',
          priority=:priority,timeout_seconds=:timeout,max_attempts=:attempts,available_at=now(),
          version=version+1,updated_at=now() WHERE id=:id AND tenant_id=:tenant
          AND state='APPROVED' RETURNING *"""), {"id": task_id, "tenant": tenant_id,
          "priority": priority, "timeout": timeout_seconds, "attempts": max_attempts})).mappings().first()
        if row is None:
            raise ControllerError("invalid task state transition")
        await self.append_audit(task_id, tenant_id, "task.queued", {"priority": priority})
        await self.session.commit()
        return dict(row)

    async def reject(self, task_id: UUID, tenant_id: str, actor: str) -> dict[str, Any]:
        return await self.transition(task_id, tenant_id, ("AWAITING_APPROVAL",), "FAILED",
                                     "task.rejected")

    async def cancel(self, task_id: UUID, tenant_id: str) -> dict[str, Any]:
        return await self.transition(task_id, tenant_id,
            ("CREATED", "AWAITING_APPROVAL", "APPROVED", "QUEUED", "SUSPENDED"),
            "CANCELLED", "task.cancelled")

    async def suspend(self, task_id: UUID, tenant_id: str) -> dict[str, Any]:
        return await self.transition(task_id, tenant_id, ("QUEUED",), "SUSPENDED", "task.suspended")

    async def resume(self, task_id: UUID, tenant_id: str) -> dict[str, Any]:
        return await self.transition(task_id, tenant_id, ("SUSPENDED",), "QUEUED", "task.resumed")

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

    async def finish(self, task_id: UUID, tenant_id: str, worker: str,
                     expected_version: int, evidence: dict[str, Any]) -> dict[str, Any]:
        evidence_hash = canonical_hash(redact(evidence))
        row = (await self.session.execute(text("""
          UPDATE controller_tasks SET state='COMPLETED',lease_owner=NULL,lease_expires_at=NULL,
            version=version+1,updated_at=now() WHERE id=:id AND tenant_id=:tenant
            AND state='RUNNING' AND lease_owner=:worker AND version=:version
            AND lease_expires_at>now() RETURNING *
        """), {"id": task_id, "tenant": tenant_id, "worker": worker,
                "version": expected_version})).mappings().first()
        if row is None:
            await self.session.rollback()
            raise ControllerError("lease or version denied")
        await self.append_audit(task_id, tenant_id, "task.completed", {"evidence_hash": evidence_hash})
        await self.session.commit()
        return dict(row)

    async def fail(self, task_id: UUID, tenant_id: str, worker: str,
                   expected_version: int, error_code: str, retryable: bool) -> dict[str, Any]:
        target = "QUEUED" if retryable else "FAILED"
        row = (await self.session.execute(text("""
          UPDATE controller_tasks SET state=:target,last_error_code=:error,
            available_at=CASE WHEN :target='QUEUED' THEN now()+(LEAST(300,power(2,attempt_count)) * interval '1 second') ELSE available_at END,
            lease_owner=NULL,lease_expires_at=NULL,version=version+1,updated_at=now()
          WHERE id=:id AND tenant_id=:tenant AND state='RUNNING' AND lease_owner=:worker
            AND version=:version AND lease_expires_at>now() RETURNING *
        """), {"target": target, "error": error_code, "id": task_id, "tenant": tenant_id,
                "worker": worker, "version": expected_version})).mappings().first()
        if row is None:
            await self.session.rollback()
            raise ControllerError("lease or version denied")
        await self.append_audit(task_id, tenant_id, "task.failed", {"error_code": error_code,
                                "retryable": retryable})
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

    async def consume_approval(self, jti: str, task_id: UUID, tenant_id: str,
                               *, commit: bool = True) -> None:
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
        if commit:
            await self.session.commit()

    async def save_approval(self, *, task_id: UUID, tenant_id: str, plan_hash: str,
                            server_id: str, tools: list[str], approver: str,
                            jti: str, expires_at: datetime, commit: bool = True) -> UUID:
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
        if commit:
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

    async def execute(self, *, task_id: UUID, tenant_id: str, server_id: str, workspace: str,
                      tool: str, arguments: dict[str, Any], token: str, request_id: str,
                      correlation_id: str) -> dict[str, Any]:
        if self.tokens is None:
            raise ControllerError("approval signing key is unavailable")
        _reject_forbidden(arguments)
        if tool not in AGENT_TOOL_POLICIES.get(server_id, set()):
            raise ControllerError("tool scope denied")
        claims = self.tokens.verify(token, consume=False, task_id=str(task_id), tenant_id=tenant_id,
            server_id=server_id, workspace=workspace, tool=tool)
        task = await self.get_task(task_id, tenant_id, lock=True)
        if task["state"] != "APPROVED" or task["workspace"] != workspace:
            raise ControllerError("task scope or state denied")
        await self.consume_approval(claims["jti"], task_id, tenant_id, commit=False)
        execution_id = uuid4()
        safe_arguments = redact(arguments)
        evidence_hash = canonical_hash({"task_id": str(task_id), "server_id": server_id,
            "workspace": workspace, "tool": tool, "arguments": safe_arguments,
            "request_id": request_id, "correlation_id": correlation_id})
        await self.session.execute(text("""INSERT INTO controller_executions
          (id,task_id,tenant_id,server_id,workspace,tool,safe_arguments,request_id,
           correlation_id,evidence_hash) VALUES
          (:id,:task,:tenant,:server,:workspace,:tool,CAST(:arguments AS jsonb),:request,
           :correlation,:evidence)"""), {"id": execution_id, "task": task_id, "tenant": tenant_id,
          "server": server_id, "workspace": workspace, "tool": tool,
          "arguments": json.dumps(safe_arguments), "request": request_id,
          "correlation": correlation_id, "evidence": evidence_hash})
        await self.session.execute(text("""UPDATE controller_tasks SET state='EXECUTING',
          version=version+1,updated_at=now() WHERE id=:id AND tenant_id=:tenant"""),
          {"id": task_id, "tenant": tenant_id})
        await self.append_audit(task_id, tenant_id, "execution.accepted",
                                {"execution_id": str(execution_id), "tool": tool,
                                 "evidence_hash": evidence_hash})
        await self.session.commit()
        return {"execution_id": str(execution_id), "task_id": str(task_id), "tenant_id": tenant_id,
                "server_id": server_id, "workspace": workspace, "tool": tool,
                "safe_arguments": safe_arguments, "request_id": request_id,
                "correlation_id": correlation_id, "state": "ACCEPTED",
                "evidence_hash": evidence_hash}

    async def verification(self, execution_id: UUID, tenant_id: str) -> dict[str, Any]:
        if self.tokens is None:
            raise ControllerError("verification signing key is unavailable")
        execution = await self.get_execution(execution_id, tenant_id)
        checks = {"APPROVAL_TOKEN": "PASS", "TOOL_ALLOWLIST": "PASS",
                  "TENANT_SCOPE": "PASS", "OUTPUT_REDACTION": "PASS"}
        code = f"VRF-{uuid4().hex[:20]}"
        unsigned = {"verification_code": code, "task_id": str(execution["task_id"]),
            "execution_id": str(execution_id), "tenant_id": tenant_id, "checks": checks,
            "evidence_hash": execution["evidence_hash"]}
        signature = hmac.new(self.tokens._secret,
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        record = {**unsigned, "signature": signature}
        await self.save_verification(record)
        return record

    async def get_execution(self, execution_id: UUID, tenant_id: str) -> dict[str, Any]:
        row = (await self.session.execute(text("""SELECT * FROM controller_executions
          WHERE id=:id AND tenant_id=:tenant"""), {"id": execution_id,
          "tenant": tenant_id})).mappings().first()
        if row is None:
            raise ControllerError("execution not found")
        return dict(row)

    async def get_verification(self, code: str, tenant_id: str) -> dict[str, Any]:
        row = (await self.session.execute(text("""SELECT * FROM controller_verifications
          WHERE verification_code=:code AND tenant_id=:tenant"""), {"code": code,
          "tenant": tenant_id})).mappings().first()
        if row is None:
            raise ControllerError("verification not found")
        return dict(row)

    async def get_audit(self, task_id: UUID, tenant_id: str) -> list[dict[str, Any]]:
        await self.get_task(task_id, tenant_id)
        rows = (await self.session.execute(text("""SELECT task_id,tenant_id,sequence,action,
          safe_details AS details,previous_hash,record_hash,correlation_id,created_at
          FROM controller_task_audit WHERE task_id=:id AND tenant_id=:tenant ORDER BY sequence"""),
          {"id": task_id, "tenant": tenant_id})).mappings().all()
        return [dict(row) for row in rows]
