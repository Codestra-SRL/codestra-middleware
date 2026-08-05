from concurrent.futures import ThreadPoolExecutor
from statistics import quantiles
from time import perf_counter

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.supervisor.security import SupervisorPrincipal, require_supervisor


def test_30_supervisor_synthetic_load_p95_under_1500ms():
    old_secret = settings.middleware_secret
    settings.middleware_secret = "load-test-only"
    app.dependency_overrides[require_supervisor] = lambda: SupervisorPrincipal(
        "load-user", "TENANT-SYN", "WORKSPACE-SYN",
        frozenset({"CALL_CENTER_MANAGER"}), frozenset({"TEAM-1", "TEAM-2", "TEAM-3"}),
        frozenset({"CMP-1", "CMP-2", "CMP-3", "CMP-4"}),
    )

    def request_once(_: int) -> float:
        start = perf_counter()
        with TestClient(app, headers={"Authorization": "Bearer load-test-only"}) as client:
            response = client.get("/api/v1/supervisor/overview")
            assert response.status_code == 200
        return (perf_counter() - start) * 1000

    try:
        with ThreadPoolExecutor(max_workers=30) as pool:
            durations = list(pool.map(request_once, range(120)))
        p95 = quantiles(durations, n=100)[94]
        print(f"SUPERVISOR_OVERVIEW_P95_MS={p95:.2f}")
        assert p95 < 1500
    finally:
        app.dependency_overrides.clear()
        settings.middleware_secret = old_secret
