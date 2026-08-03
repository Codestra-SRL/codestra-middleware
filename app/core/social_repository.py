"""PostgreSQL repository for the durable social publishing control plane."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.social_postly import SocialError


def _digest(value: dict[str, Any] | str) -> str:
    raw = (
        value
        if isinstance(value, str)
        else json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=lambda item: (
                item.isoformat() if isinstance(item, datetime) else str(item)
            ),
        )
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class SocialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        job_id = uuid4()
        row = (
            (
                await self.session.execute(
                    text("""
            INSERT INTO social_content_job
              (id,organization_id,workspace_id,campaign_id,content_job_id,current_version,
               integration_ids,preferred_language,correlation_id,state,scheduled_at)
            VALUES (:id,:organization_id,:workspace_id,:campaign_id,:content_job_id,:content_version,
                    CAST(:integration_ids_json AS jsonb),:preferred_language,:correlation_id,'generating',:scheduled_at)
            ON CONFLICT (organization_id,content_job_id) DO UPDATE
              SET content_job_id=EXCLUDED.content_job_id
            RETURNING id,content_job_id,current_version,state,correlation_id
        """),
                    {
                        "id": job_id,
                        "integration_ids_json": json.dumps(request["integration_ids"]),
                        **request,
                    },
                )
            )
            .mappings()
            .one()
        )
        await self._audit(
            row["id"],
            "n8n_generation_queued",
            None,
            "generating",
            "odoo",
            row["correlation_id"],
        )
        await self.session.commit()
        return dict(row)

    async def store_proposal(
        self,
        public_id: str,
        proposal: dict[str, Any],
        execution_id: str,
        organization_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        job = await self._job(public_id, organization_id, workspace_id, for_update=True)
        if (
            proposal["content_job_id"] != public_id
            or proposal["content_version"] != job["current_version"]
        ):
            raise SocialError("STALE_N8N_RESULT", "n8n result binding conflict")
        if job["state"] not in {"generating", "pending_review"}:
            raise SocialError("N8N_STATE_CONFLICT", "job is not accepting proposals")
        version_id = uuid4()
        await self.session.execute(
            text("""
            INSERT INTO social_content_version
              (id,job_id,version,proposal,proposal_sha256,workflow_execution_id)
            VALUES (:id,:job_id,:version,CAST(:proposal AS jsonb),:digest,:execution_id)
            ON CONFLICT (job_id,version) DO NOTHING
        """),
            {
                "id": version_id,
                "job_id": job["id"],
                "version": proposal["content_version"],
                "proposal": json.dumps(proposal),
                "digest": _digest(proposal),
                "execution_id": execution_id,
            },
        )
        await self.session.execute(
            text(
                "UPDATE social_content_job SET state='pending_review',updated_at=now() WHERE id=:id"
            ),
            {"id": job["id"]},
        )
        await self._audit(
            job["id"],
            "n8n_proposal_received",
            job["state"],
            "pending_review",
            "n8n",
            job["correlation_id"],
            {"workflow_execution_id": execution_id},
        )
        await self.session.commit()
        return await self.get_job(public_id, organization_id, workspace_id)

    async def approve(
        self,
        public_id: str,
        approval: dict[str, Any],
        organization_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        job = await self._job(public_id, organization_id, workspace_id, for_update=True)
        if (
            job["state"] != "pending_review"
            or approval["content_version"] != job["current_version"]
        ):
            raise SocialError(
                "APPROVAL_STATE_CONFLICT", "approval does not bind current version"
            )
        version_id = (
            await self.session.execute(
                text(
                    "SELECT id FROM social_content_version WHERE job_id=:job_id AND version=:version"
                ),
                {"job_id": job["id"], "version": job["current_version"]},
            )
        ).scalar_one()
        payload = {
            "approval_public_id": approval["approval_id"],
            "approved_by": approval["approved_by"],
            "approved_at": approval["approved_at"],
            "content_version": approval["content_version"],
        }
        await self.session.execute(
            text("""
            INSERT INTO social_approval
              (id,job_id,content_version_id,approval_public_id,approved_by,approved_at,decision,approval_sha256)
            VALUES (:id,:job_id,:version_id,:approval_public_id,:approved_by,:approved_at,'approved',:digest)
        """),
            {
                "id": uuid4(),
                "job_id": job["id"],
                "version_id": version_id,
                "digest": _digest(payload),
                **payload,
            },
        )
        await self.session.execute(
            text(
                "UPDATE social_content_job SET state='approved',updated_at=now() WHERE id=:id"
            ),
            {"id": job["id"]},
        )
        await self._audit(
            job["id"],
            "human_approved",
            "pending_review",
            "approved",
            approval["approved_by"],
            job["correlation_id"],
            {"approval_id": approval["approval_id"]},
        )
        await self.session.commit()
        return await self.get_job(public_id, organization_id, workspace_id)

    async def claim_publications(
        self,
        public_id: str,
        integration_ids: list[str],
        organization_id: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        job = await self._job(public_id, organization_id, workspace_id, for_update=True)
        if job["state"] not in {"approved", "queued"}:
            raise SocialError(
                "APPROVAL_REQUIRED", "approved immutable version required"
            )
        version_id = (
            await self.session.execute(
                text(
                    "SELECT id FROM social_content_version WHERE job_id=:id AND version=:version"
                ),
                {"id": job["id"], "version": job["current_version"]},
            )
        ).scalar_one()
        approval_id = (
            await self.session.execute(
                text(
                    "SELECT id FROM social_approval WHERE content_version_id=:id AND decision='approved'"
                ),
                {"id": version_id},
            )
        ).scalar_one()
        publications: list[dict[str, Any]] = []
        inserted_count = 0
        for integration_id in sorted(set(integration_ids)):
            raw = "|".join(
                (
                    job["organization_id"],
                    public_id,
                    str(job["current_version"]),
                    integration_id,
                    job["scheduled_at"].isoformat(),
                )
            )
            claim = _digest(raw)
            claim_id, publication_id = uuid4(), uuid4()
            inserted = (
                await self.session.execute(
                    text("""
                INSERT INTO social_idempotency_claim
                  (id,organization_id,content_job_id,content_version,integration_id,scheduled_at,claim_sha256)
                VALUES (:id,:organization_id,:content_job_id,:version,:integration_id,:scheduled_at,:claim)
                ON CONFLICT (claim_sha256) DO NOTHING RETURNING id
            """),
                    {
                        "id": claim_id,
                        "organization_id": job["organization_id"],
                        "content_job_id": public_id,
                        "version": job["current_version"],
                        "integration_id": integration_id,
                        "scheduled_at": job["scheduled_at"],
                        "claim": claim,
                    },
                )
            ).scalar_one_or_none()
            if inserted:
                inserted_count += 1
                await self.session.execute(
                    text("""
                    INSERT INTO social_publication
                      (id,job_id,content_version_id,approval_id,integration_id,state)
                    VALUES (:id,:job_id,:version_id,:approval_id,:integration_id,'queued')
                """),
                    {
                        "id": publication_id,
                        "job_id": job["id"],
                        "version_id": version_id,
                        "approval_id": approval_id,
                        "integration_id": integration_id,
                    },
                )
                await self.session.execute(
                    text(
                        "UPDATE social_idempotency_claim SET publication_id=:publication_id WHERE id=:id"
                    ),
                    {"publication_id": publication_id, "id": claim_id},
                )
            row = (
                (
                    await self.session.execute(
                        text("""
                SELECT p.id,p.integration_id,p.state,p.postly_group_id,p.provider_release_id,p.attempt_count
                FROM social_idempotency_claim c JOIN social_publication p ON p.id=c.publication_id
                WHERE c.claim_sha256=:claim
            """),
                        {"claim": claim},
                    )
                )
                .mappings()
                .one()
            )
            publications.append(dict(row))
        if inserted_count:
            await self.session.execute(
                text(
                    "UPDATE social_content_job SET state='queued',updated_at=now() WHERE id=:id"
                ),
                {"id": job["id"]},
            )
            await self._audit(
                job["id"],
                "publication_claimed",
                "approved",
                "queued",
                "middleware",
                job["correlation_id"],
                {"integration_count": inserted_count},
            )
        await self.session.commit()
        return publications

    async def record_result(self, publication_id: UUID, result: dict[str, Any]) -> None:
        state = result["state"]
        await self.session.execute(
            text("""
            UPDATE social_publication SET state=:state,postly_group_id=:group_id,
              provider_release_id=:release_id,provider_result=CAST(:result AS jsonb),
              lease_owner=NULL,lease_expires_at=NULL,updated_at=now() WHERE id=:id
        """),
            {
                "id": publication_id,
                "state": state,
                "group_id": result.get("postly_group_id"),
                "release_id": result.get("provider_release_id"),
                "result": json.dumps(result),
            },
        )
        await self.session.commit()

    async def record_failure(
        self, publication_id: UUID, *, category: str, code: str, retryable: bool
    ) -> str:
        row = (
            (
                await self.session.execute(
                    text(
                        "UPDATE social_publication SET attempt_count=attempt_count+1 WHERE id=:id RETURNING attempt_count"
                    ),
                    {"id": publication_id},
                )
            )
            .mappings()
            .one()
        )
        attempt = row["attempt_count"]
        status = "retry_wait" if retryable and attempt < 3 else "dead_letter"
        delay = min(300, 5 * (2 ** (attempt - 1))) + random.uniform(0, 1)
        await self.session.execute(
            text("""
            UPDATE social_publication SET state=:state,last_error_category=:category,
              next_attempt_at=:next_attempt,lease_owner=NULL,lease_expires_at=NULL,updated_at=now()
            WHERE id=:id
        """),
            {
                "id": publication_id,
                "state": status,
                "category": category,
                "next_attempt": datetime.now(timezone.utc)  # noqa: UP017
                + timedelta(seconds=delay)
                if status == "retry_wait"
                else None,
            },
        )
        await self.session.execute(
            text("""
            INSERT INTO social_delivery_attempt
              (id,publication_id,attempt_number,status,safe_error_code,error_category,retryable)
            VALUES (:id,:publication_id,:attempt,:status,:code,:category,:retryable)
        """),
            {
                "id": uuid4(),
                "publication_id": publication_id,
                "attempt": attempt,
                "status": status,
                "code": code,
                "category": category,
                "retryable": retryable,
            },
        )
        if status == "dead_letter":
            await self.session.execute(
                text("""
                INSERT INTO social_dead_letter (id,publication_id,reason_code,safe_details)
                VALUES (:id,:publication_id,:code,'{}'::jsonb)
                ON CONFLICT (publication_id) DO NOTHING
            """),
                {"id": uuid4(), "publication_id": publication_id, "code": code},
            )
        await self.session.commit()
        return status

    async def require_reconciliation(self, publication_id: UUID) -> None:
        await self.session.execute(
            text(
                "UPDATE social_publication SET state='unknown_requires_reconciliation',updated_at=now() WHERE id=:id"
            ),
            {"id": publication_id},
        )
        await self.session.execute(
            text("""
            INSERT INTO social_reconciliation_lease (id,publication_id,status,next_attempt_at)
            VALUES (:id,:publication_id,'pending',now()) ON CONFLICT (publication_id) DO NOTHING
        """),
            {"id": uuid4(), "publication_id": publication_id},
        )
        await self.session.commit()

    async def claim_reconciliation(
        self, owner: str, lease_seconds: int = 60
    ) -> dict[str, Any] | None:
        row = (
            (
                await self.session.execute(
                    text("""
            WITH candidate AS (
              SELECT id FROM social_reconciliation_lease
              WHERE status IN ('pending','retry_wait') AND COALESCE(next_attempt_at,now())<=now()
                AND (lease_expires_at IS NULL OR lease_expires_at<=now())
              ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE social_reconciliation_lease r SET status='leased',lease_owner=:owner,
              lease_expires_at=now() + make_interval(secs=>:seconds),attempt_count=attempt_count+1,
              updated_at=now() FROM candidate WHERE r.id=candidate.id RETURNING r.*
        """),
                    {"owner": owner, "seconds": lease_seconds},
                )
            )
            .mappings()
            .one_or_none()
        )
        await self.session.commit()
        return dict(row) if row else None

    async def get_job(
        self, public_id: str, organization_id: str, workspace_id: str
    ) -> dict[str, Any]:
        return dict(await self._job(public_id, organization_id, workspace_id))

    async def get_audit(
        self, public_id: str, organization_id: str, workspace_id: str
    ) -> list[dict[str, Any]]:
        job = await self._job(public_id, organization_id, workspace_id)
        rows = (
            (
                await self.session.execute(
                    text("""
                SELECT sequence,action,from_state,to_state,actor_ref,occurred_at,
                       correlation_id,safe_details
                FROM social_audit_record WHERE job_id=:job_id ORDER BY sequence
                """),
                    {"job_id": job["id"]},
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    async def get_analytics(
        self, public_id: str, organization_id: str, workspace_id: str
    ) -> dict[str, int]:
        job = await self._job(public_id, organization_id, workspace_id)
        row = (
            (
                await self.session.execute(
                    text("""
                SELECT COALESCE(SUM((provider_result->>'impressions')::bigint),0) impressions,
                       COALESCE(SUM((provider_result->>'reactions')::bigint),0) reactions,
                       COALESCE(SUM((provider_result->>'comments')::bigint),0) comments,
                       COALESCE(SUM((provider_result->>'shares')::bigint),0) shares
                FROM social_publication WHERE job_id=:job_id
                """),
                    {"job_id": job["id"]},
                )
            )
            .mappings()
            .one()
        )
        return {key: int(value) for key, value in row.items()}

    async def accept_provider_callback(
        self, callback: dict[str, Any], payload_sha256: str
    ) -> dict[str, Any]:
        callback_id = callback["callback_id"]
        if (
            await self.session.execute(
                text("SELECT 1 FROM social_provider_callback WHERE callback_id=:id"),
                {"id": callback_id},
            )
        ).scalar_one_or_none():
            raise SocialError(
                "CALLBACK_REPLAY", "provider callback replay rejected", 409
            )
        prior_event = (
            await self.session.execute(
                text(
                    "SELECT callback_id FROM social_provider_callback WHERE event_id=:id"
                ),
                {"id": callback["event_id"]},
            )
        ).scalar_one_or_none()
        if prior_event:
            return {"status": "duplicate_event", "persisted": False}
        releases = [
            item.get("provider_release_id")
            for item in callback["provider_results"]
            if item.get("provider_release_id")
        ]
        groups = (
            [callback.get("postly_group_id")] if callback.get("postly_group_id") else []
        )
        if not releases and not groups:
            raise SocialError(
                "CALLBACK_BINDING_REQUIRED", "provider binding required", 409
            )
        matched_publications: list[dict[str, Any]] = []
        for result in callback["provider_results"]:
            rows = (
                (
                    await self.session.execute(
                        text("""
                        SELECT p.id publication_id,p.job_id,j.*
                        FROM social_publication p
                        JOIN social_content_job j ON j.id=p.job_id
                        WHERE p.integration_id=:integration_id
                          AND (
                            (CAST(:release_id AS text) IS NOT NULL
                             AND p.provider_release_id=CAST(:release_id AS text))
                            OR (CAST(:group_id AS text) IS NOT NULL
                                AND p.postly_group_id=CAST(:group_id AS text))
                          )
                        """),
                        {
                            "integration_id": result["integration_id"],
                            "release_id": result.get("provider_release_id"),
                            "group_id": callback.get("postly_group_id"),
                        },
                    )
                )
                .mappings()
                .all()
            )
            if len(rows) != 1:
                raise SocialError(
                    "CALLBACK_BINDING_CONFLICT", "provider binding conflict", 409
                )
            matched_publications.append(dict(rows[0]))
        job_ids = {item["job_id"] for item in matched_publications}
        if len(job_ids) != 1:
            raise SocialError(
                "CALLBACK_BINDING_CONFLICT", "provider binding conflict", 409
            )
        bound = matched_publications[0]
        try:
            await self.session.execute(
                text("""
                INSERT INTO social_provider_callback
                  (callback_id,event_id,job_id,correlation_id,payload_sha256,state,attempt,occurred_at)
                VALUES (:callback_id,:event_id,:job_id,:correlation_id,:payload_sha256,
                        :state,:attempt,:occurred_at)
                """),
                {"job_id": bound["id"], "payload_sha256": payload_sha256, **callback},
            )
        except IntegrityError as exc:
            await self.session.rollback()
            raise SocialError(
                "CALLBACK_REPLAY", "provider callback replay rejected", 409
            ) from exc
        for result, publication in zip(
            callback["provider_results"], matched_publications, strict=True
        ):
            await self.session.execute(
                text("""
                UPDATE social_publication SET state=:state,
                  provider_release_id=COALESCE(:release_id,provider_release_id),
                  updated_at=now()
                WHERE id=:publication_id
                """),
                {
                    "publication_id": publication["publication_id"],
                    "state": result["state"],
                    "release_id": result.get("provider_release_id"),
                },
            )
        await self._audit(
            bound["id"],
            "provider_callback_accepted",
            bound["state"],
            callback["state"],
            "postly-adapter",
            callback["correlation_id"],
            {"callback_id": str(callback_id), "attempt": callback["attempt"]},
        )
        await self.session.commit()
        return {"status": "accepted", "persisted": True}

    async def _job(
        self,
        public_id: str,
        organization_id: str,
        workspace_id: str,
        *,
        for_update: bool = False,
    ) -> Any:
        suffix = " FOR UPDATE" if for_update else ""
        row = (
            (
                await self.session.execute(
                    text(
                        "SELECT * FROM social_content_job WHERE content_job_id=:id "
                        "AND organization_id=:organization_id "
                        "AND workspace_id=:workspace_id" + suffix
                    ),
                    {
                        "id": public_id,
                        "organization_id": organization_id,
                        "workspace_id": workspace_id,
                    },
                )
            )
            .mappings()
            .one_or_none()
        )
        if not row:
            raise SocialError("JOB_NOT_FOUND", "social job not found", 404)
        return row

    async def _audit(
        self,
        job_id: UUID,
        action: str,
        from_state: str | None,
        to_state: str,
        actor: str,
        correlation_id: str,
        safe: dict[str, Any] | None = None,
    ) -> None:
        sequence = (
            await self.session.execute(
                text(
                    "SELECT COALESCE(MAX(sequence),0)+1 FROM social_audit_record WHERE job_id=:id"
                ),
                {"id": job_id},
            )
        ).scalar_one()
        await self.session.execute(
            text("""
            INSERT INTO social_audit_record
              (id,job_id,sequence,action,from_state,to_state,actor_ref,correlation_id,safe_details)
            VALUES (:id,:job_id,:sequence,:action,:from_state,:to_state,:actor,:correlation_id,CAST(:safe AS jsonb))
        """),
            {
                "id": uuid4(),
                "job_id": job_id,
                "sequence": sequence,
                "action": action,
                "from_state": from_state,
                "to_state": to_state,
                "actor": actor,
                "correlation_id": correlation_id,
                "safe": json.dumps(safe or {}),
            },
        )
