from fastapi.testclient import TestClient
import pytest

from app.core.config import settings
from app.main import app
from app.supervisor.security import SupervisorPrincipal, require_supervisor
from app.supervisor.service import STORE

TOKEN = "test-only-bearer"


def principal(team="TEAM-1", tenant="TENANT-SYN", roles=("CALL_CENTER_SUPERVISOR",)):
    return SupervisorPrincipal(
        "user-1",
        tenant,
        "WORKSPACE-SYN",
        frozenset(roles),
        frozenset({team}),
        frozenset({"CMP-1"}),
    )


@pytest.fixture(autouse=True)
def isolated_auth():
    old = settings.middleware_secret
    settings.middleware_secret = TOKEN
    app.dependency_overrides[require_supervisor] = lambda: principal()
    yield
    app.dependency_overrides.clear()
    settings.middleware_secret = old


def client():
    return TestClient(app, headers={"Authorization": f"Bearer {TOKEN}"})


def test_overview_and_team_scope():
    response = client().get("/api/v1/supervisor/overview")
    assert response.status_code == 200
    assert response.json()["agents_logged_in"] == 10
    agents = client().get("/api/v1/supervisor/agents").json()["items"]
    assert agents and {a["team_id"] for a in agents} == {"TEAM-1"}


def test_cross_tenant_and_cross_team_are_indistinguishable():
    app.dependency_overrides[require_supervisor] = lambda: principal(tenant="OTHER")
    assert client().get("/api/v1/supervisor/agents/AGT-003").status_code == 404
    app.dependency_overrides[require_supervisor] = lambda: principal(team="TEAM-2")
    assert client().get("/api/v1/supervisor/agents/AGT-003").status_code == 404


def test_coaching_is_human_audited_and_idempotent():
    headers = {"Idempotency-Key": "idem-supervisor-0001"}
    body = {"reason": "QA follow-up", "note": "Review synthetic call handling"}
    first = client().post(
        "/api/v1/supervisor/agents/AGT-003/coaching-note", headers=headers, json=body
    )
    second = client().post(
        "/api/v1/supervisor/agents/AGT-003/coaching-note", headers=headers, json=body
    )
    assert first.status_code == second.status_code == 202
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert STORE.audits[-1]["action"] == "coaching.create"


def test_agent_and_campaign_commands_fail_closed():
    body = {"reason": "synthetic authorization test"}
    assert (
        client()
        .post("/api/v1/supervisor/agents/AGT-003/status-refresh", json=body)
        .status_code
        == 403
    )
    assert (
        client()
        .post("/api/v1/supervisor/campaigns/CMP-1/activate", json=body)
        .status_code
        == 403
    )


def test_qa_requires_human_role():
    assert client().get("/api/v1/supervisor/qa").status_code == 403
    app.dependency_overrides[require_supervisor] = lambda: principal(
        roles=("QA_REVIEWER",)
    )
    assert client().get("/api/v1/supervisor/qa").status_code == 200


def test_sse_is_scoped_and_sequenced():
    with client().stream(
        "GET", "/api/v1/supervisor/events?last_event_id=40"
    ) as response:
        body = b"".join(response.iter_bytes()).decode()
    assert response.status_code == 200
    assert "id: 41" in body and '"tenant_id":"TENANT-SYN"' in body
    assert "TEAM-2" not in body


def test_dependency_override_cleanup_contract():
    assert require_supervisor in app.dependency_overrides


def test_synthetic_cardinality():
    assert len(STORE.agents) == 30
    assert len(STORE.campaigns) == 4
    assert len(STORE.calls) == 100
    assert len(STORE.callbacks) == 50
    assert len(STORE.qa) == 30
    assert len(STORE.compliance) == 10
    assert len(STORE.coaching) >= 20
