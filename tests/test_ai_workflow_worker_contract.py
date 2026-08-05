from pathlib import Path

from app.workers.ai_workflow import new_worker_identity

ROOT = Path(__file__).parents[1]


def test_worker_uses_skip_locked_durable_leases_and_bounded_claims():
    source = (ROOT / "app/workers/ai_workflow.py").read_text()
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "lease_expires_at" in source
    assert "range(1, 11)" in source or "range(1,11)" in source
    assert new_worker_identity().startswith("ai-workflow-worker-")


def test_worker_has_no_external_delivery_or_in_memory_queue():
    source = (ROOT / "app/workers/ai_workflow.py").read_text().lower()
    for forbidden in (
        "requests",
        "httpx",
        "deque",
        "asyncio.queue",
        "send_email",
        "publish",
    ):
        assert forbidden not in source
