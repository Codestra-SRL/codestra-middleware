#!/usr/bin/env python3
"""Run one bounded synthetic event through the real governed n8n webhook."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from sqlalchemy import text

from app.core.config import settings
from app.core.n8n_runtime import canonical_bytes, ExecutionStatus
from app.db.session import SessionFactory, engine
from app.workers.n8n_runtime import claim, dispatch_one
from app.workers.social_n8n_delivery import reconcile_terminal, stage_pending


async def main() -> None:
    dangerous = {
        "social_publish": settings.social_publish_enabled,
        "social_production_canary": settings.social_production_canary_enabled,
        "social_odoo_write": settings.social_odoo_write_enabled,
        "vicidial_production": getattr(settings, "vicidial_production_enabled", False),
        "automatic_contacting": settings.automatic_contacting_enabled,
        "hootsuite": settings.hootsuite_enabled,
    }
    if any(dangerous.values()):
        raise RuntimeError("dangerous output flag enabled")
    required = (
        settings.identity_graph_enabled,
        settings.lead_intelligence_enabled,
        settings.next_best_action_enabled,
        settings.attribution_engine_enabled,
        settings.n8n_runtime_enabled,
    )
    if not all(required):
        raise RuntimeError("isolated synthetic feature gate unavailable")

    tenant_id, campaign_id, content_id = uuid4(), uuid4(), uuid4()
    event_id, correlation_id, delivery_id = str(uuid4()), str(uuid4()), uuid4()
    occurred_at = datetime.now(UTC).isoformat()
    payload = {
        "event_id": event_id,
        "event_type": "social.message.received",
        "event_version": 1,
        "occurred_at": occurred_at,
        "correlation_id": correlation_id,
        "tenant_id": str(tenant_id),
        "source": "social",
        "provider": "postly",
        "subject_id": "synthetic-profile-n8-http",
        "payload": {
            "name": "Synthetic Customer",
            "email": "synthetic-lead@example.invalid",
            "phone": "+15555550100",
            "message": "I need a quote for shipping next week.",
            "network": "facebook",
            "social_profile_id": "synthetic-profile-n8-http",
            "campaign_id": str(campaign_id),
            "content_id": str(content_id),
            "consent_status": "UNKNOWN",
            "dnc_status": "CLEAR",
            "synthetic": True,
        },
    }
    payload_hash = hashlib.sha256(canonical_bytes(payload)).hexdigest()

    async with SessionFactory() as session:
        await session.execute(
            text("""INSERT INTO n8n_workflow_registry
                (registry_id,workflow_code,workflow_version,n8n_workflow_id,
                 event_types,tenant_scope,enabled,timeout_seconds,retry_policy,
                 result_contract,owner,webhook_path)
                VALUES (:id,'CDST_SOCIAL_EVENT_ROUTER','1',
                 'CdstPhaseN8BusinessCanaryV1',CAST(:events AS jsonb),
                 CAST(:tenants AS jsonb),true,120,CAST(:retry AS jsonb),
                 'codestra.n8n.result.v1','phase-n8-canary',
                 '/webhook/codestra-social-router-v1')
                ON CONFLICT (workflow_code,workflow_version) DO UPDATE SET
                 tenant_scope=EXCLUDED.tenant_scope,enabled=true,
                 n8n_workflow_id=EXCLUDED.n8n_workflow_id,
                 webhook_path=EXCLUDED.webhook_path"""),
            {"id": uuid4(), "events": json.dumps([payload["event_type"]]),
             "tenants": json.dumps([str(tenant_id)]), "retry": json.dumps({"max_attempts": 3})},
        )
        inserted = await session.scalar(
            text("""INSERT INTO integration_event
                (idempotency_key,event_type,schema_version,original_event_id,
                 entity_key,source_system,correlation_id,payload_json,payload_hash,state)
                VALUES (:key,:type,'1.0',:event,:entity,'social',:correlation,
                 CAST(:payload AS jsonb),:hash,'queued') RETURNING id"""),
            {"key": f"phase-n8-http-{event_id}", "type": payload["event_type"],
             "event": event_id, "entity": f"synthetic:phase-n8:http:{event_id}",
             "correlation": correlation_id, "payload": json.dumps(payload), "hash": payload_hash},
        )
        await session.execute(
            text("""INSERT INTO integration_delivery
                (id,event_id,target,status,attempts,max_attempts,available_at)
                VALUES (:id,:event,'n8n','pending',0,3,now())"""),
            {"id": delivery_id, "event": inserted},
        )
        await session.commit()
        if await stage_pending(session) != 1:
            raise RuntimeError("synthetic delivery was not staged")
        executions = await claim(session, 1)
        if len(executions) != 1:
            raise RuntimeError("governed execution was not claimed")
        execution_id = executions[0].execution_id
        async with httpx.AsyncClient(timeout=120) as client:
            submitted = await dispatch_one(session, executions[0], client)
        if not submitted:
            raise RuntimeError("authenticated n8n webhook dispatch failed")

        for _ in range(60):
            await asyncio.sleep(1)
            await session.refresh(executions[0])
            if executions[0].status in {
                ExecutionStatus.COMPLETED, ExecutionStatus.FAILED,
                ExecutionStatus.DEAD_LETTER, ExecutionStatus.TIMED_OUT,
            }:
                break
        await reconcile_terminal(session)
        result = (
            await session.execute(
                text("""SELECT e.status,e.n8n_execution_id,d.status AS delivery_status,
                    r.result_json FROM n8n_runtime_execution e
                    JOIN social_n8n_delivery_execution m USING (execution_id)
                    JOIN integration_delivery d ON d.id=m.delivery_id
                    LEFT JOIN n8n_runtime_result r USING (execution_id)
                    WHERE e.execution_id=:id"""),
                {"id": execution_id},
            )
        ).mappings().one()
        if result["status"] != "COMPLETED" or result["delivery_status"] != "delivered":
            raise RuntimeError(f"workflow terminal state is {result['status']}/{result['delivery_status']}")
        business = (result["result_json"] or {}).get("result", {})
        audit_count = await session.scalar(
            text("SELECT count(*) FROM lead_pipeline_audit_events WHERE correlation_id=:id"),
            {"id": correlation_id},
        )
        if not audit_count or audit_count < 8:
            raise RuntimeError("immutable audit trace is incomplete")
        print(json.dumps({
            "event_accepted": True, "tenant_id": str(tenant_id),
            "campaign_id": str(campaign_id), "content_id": str(content_id),
            "event_id": event_id, "correlation_id": correlation_id,
            "delivery_id": str(delivery_id), "execution_id": str(execution_id),
            "n8n_execution_id": result["n8n_execution_id"],
            "person_id": business.get("person_id"), "lead_id": business.get("lead_id"),
            "revenue_event_id": business.get("revenue_event_id"),
            "attribution_calculation_ids": business.get("attribution_calculation_ids"),
            "audit_event_count": audit_count, "external_actions": 0,
            "dangerous_flags": dangerous,
        }, sort_keys=True))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
