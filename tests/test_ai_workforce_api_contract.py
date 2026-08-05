import asyncio

import pytest
from fastapi import HTTPException

from app.api.v1.ai_workforce import DispatchIntent, dispatch


def test_dispatch_api_remains_fail_closed_when_platform_disabled():
    intent = DispatchIntent(workspace_id="w1", employee_id="e1", department_id="d1", goal_id="g1", task_id="t1", workflow_code="CDA-AI-01", workflow_version="1", idempotency_key="i1", trace_id="tr1", employee_active=True, department_active=True, goal_active=True, permission_granted=True, approval_required=False, workflow_approved=True)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(dispatch(intent, tenant_id="tenant-a"))
    assert exc.value.status_code == 404

