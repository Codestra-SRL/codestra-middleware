from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from fastapi import HTTPException

from app.supervisor.security import SupervisorPrincipal


@dataclass
class SupervisorStore:
    agents: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    campaigns: list[dict[str, Any]] = field(default_factory=list)
    callbacks: list[dict[str, Any]] = field(default_factory=list)
    qa: list[dict[str, Any]] = field(default_factory=list)
    compliance: list[dict[str, Any]] = field(default_factory=list)
    coaching: list[dict[str, Any]] = field(default_factory=list)
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=5000))
    audits: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=5000))
    idempotency: dict[str, dict[str, Any]] = field(default_factory=dict)
    sequence: int = 0
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)

    def scoped(
        self, rows: list[dict[str, Any]], principal: SupervisorPrincipal
    ) -> list[dict[str, Any]]:
        return [
            row
            for row in rows
            if row["tenant_id"] == principal.tenant_id
            and row["workspace_id"] == principal.workspace_id
            and (
                "CALL_CENTER_MANAGER" in principal.roles
                or row.get("team_id") in principal.team_ids
            )
        ]

    def get(
        self, rows: list[dict[str, Any]], row_id: str, principal: SupervisorPrincipal
    ) -> dict[str, Any]:
        for row in self.scoped(rows, principal):
            if row["id"] == row_id:
                return row
        raise HTTPException(404, "resource not found")

    def mutate(
        self,
        *,
        action: str,
        resource: dict[str, Any],
        principal: SupervisorPrincipal,
        idempotency_key: str,
        reason: str,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        if len(idempotency_key) < 16 or not reason.strip():
            raise HTTPException(422, "reason and idempotency key required")
        digest = sha256(
            f"{principal.tenant_id}:{action}:{idempotency_key}".encode()
        ).hexdigest()
        if digest in self.idempotency:
            return {**self.idempotency[digest], "duplicate": True}
        resource.update(changes)
        result = {"accepted": True, "duplicate": False, "resource_id": resource["id"]}
        self.idempotency[digest] = result
        self.audits.append(
            {
                "action": action,
                "subject": principal.subject,
                "tenant_id": principal.tenant_id,
                "workspace_id": principal.workspace_id,
                "resource_id": resource["id"],
                "reason": reason[:256],
                "occurred_at": datetime.now(UTC).isoformat(),
            }
        )
        return result


def synthetic_store() -> SupervisorStore:
    store = SupervisorStore()
    tenant, workspace = "TENANT-SYN", "WORKSPACE-SYN"
    states = ("READY", "ON_CALL", "PAUSED", "WRAP_UP", "UNAVAILABLE")
    store.agents = [
        {
            "id": f"AGT-{i:03}",
            "tenant_id": tenant,
            "workspace_id": workspace,
            "team_id": f"TEAM-{(i % 3) + 1}",
            "name": f"Synthetic Agent {i:02}",
            "extension": str(6100 + i),
            "campaign_id": f"CMP-{(i % 4) + 1}",
            "state": states[i % len(states)],
            "state_duration_seconds": i * 17,
            "calls_today": i % 12,
            "occupancy": 0.85 + (i % 7) / 100,
            "adherence": 0.90 + (i % 6) / 100,
            "qa_score": 85 + i % 12,
            "agent_assist": "ACTIVE" if i % 3 == 0 else "IDLE",
        }
        for i in range(1, 31)
    ]
    store.campaigns = [
        {
            "id": f"CMP-{i}",
            "tenant_id": tenant,
            "workspace_id": workspace,
            "team_id": f"TEAM-{((i - 1) % 3) + 1}",
            "name": f"Synthetic Campaign {i}",
            "status": "STAGING_DISABLED",
            "active_agents": 5 + i,
            "calls_waiting": i - 1,
            "service_level": 0.82 + i / 100,
        }
        for i in range(1, 5)
    ]
    store.calls = [
        {
            "id": f"CALL-{i:04}",
            "tenant_id": tenant,
            "workspace_id": workspace,
            "team_id": f"TEAM-{(i % 3) + 1}",
            "agent_id": f"AGT-{(i % 30) + 1:03}",
            "campaign_id": f"CMP-{(i % 4) + 1}",
            "state": "ACTIVE" if i < 20 else "ENDED",
            "duration_seconds": i * 11,
            "hold_seconds": i % 13,
            "customer_reference": f"CUSTOMER-***{i % 10}",
        }
        for i in range(1, 101)
    ]
    store.callbacks = [
        {
            "id": f"CB-{i:03}",
            "tenant_id": tenant,
            "workspace_id": workspace,
            "team_id": f"TEAM-{(i % 3) + 1}",
            "campaign_id": f"CMP-{(i % 4) + 1}",
            "status": "OVERDUE" if i % 5 == 0 else "SCHEDULED",
            "attempts": i % 3,
        }
        for i in range(1, 51)
    ]
    store.qa = [
        {
            "id": f"QA-{i:03}",
            "tenant_id": tenant,
            "workspace_id": workspace,
            "team_id": f"TEAM-{(i % 3) + 1}",
            "ai_score": 80 + i % 18,
            "human_score": None,
            "status": "PENDING_HUMAN_REVIEW",
        }
        for i in range(1, 31)
    ]
    store.compliance = [
        {
            "id": f"ALERT-{i:03}",
            "tenant_id": tenant,
            "workspace_id": workspace,
            "team_id": f"TEAM-{(i % 3) + 1}",
            "severity": "HIGH" if i % 4 == 0 else "MEDIUM",
            "status": "OPEN_HUMAN_REVIEW_REQUIRED",
        }
        for i in range(1, 11)
    ]
    store.coaching = [
        {
            "id": f"COACH-{i:03}",
            "tenant_id": tenant,
            "workspace_id": workspace,
            "team_id": f"TEAM-{(i % 3) + 1}",
            "status": "DRAFT",
            "topic": "Synthetic coaching",
        }
        for i in range(1, 21)
    ]
    return store


STORE = synthetic_store()
