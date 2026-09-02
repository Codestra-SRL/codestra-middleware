from pathlib import Path

import pytest

from app.core.controller import ApprovalTokens, ControllerError, RestrictedController, TaskState


TENANT = "tenant-fixture"


@pytest.fixture
def domain(tmp_path: Path) -> RestrictedController:
    root = tmp_path / "workspace"
    root.mkdir()
    return RestrictedController(ApprovalTokens(b"fixture-scheduler-signing-key-material-0001"), (root,))


def approved(domain: RestrictedController, server: str, tool: str):
    task, _ = domain.create_task(
        {"title": "fixture", "objective": "fixture only", "workspace": str(domain.workspaces[0])},
        tenant_id=TENANT, request_id="request", correlation_id="correlation",
        idempotency_key=f"fixture-{server}-{tool}",
    )
    domain.plan(task.task_id, TENANT, [{"tool": tool, "arguments": {}}])
    domain.approve(task.task_id, TENANT, task.plan_hash, "reviewer", server)
    return task


def test_web_agent_scheduler_lease_retry_recovery_and_completion(domain):
    task = approved(domain, "web", "git_status")
    domain.queue(task.task_id, TENANT, priority=9, max_attempts=2, now=100)
    claim = domain.claim(server_id="web", worker_id="web-worker", lease_seconds=30, now=100)
    assert claim and claim.state == TaskState.RUNNING and claim.attempt_count == 1
    domain.heartbeat(task.task_id, TENANT, "web-worker", now=110)
    retry = domain.fail(task.task_id, TENANT, "web-worker", "temporary", retryable=True, now=111)
    assert retry.state == TaskState.QUEUED and retry.available_at == 113
    claim = domain.claim(server_id="web", worker_id="web-worker", lease_seconds=30, now=113)
    assert claim and claim.attempt_count == 2
    completed = domain.finish(task.task_id, TENANT, "web-worker", {"tests": "PASS"})
    assert completed.state == TaskState.COMPLETED
    assert any(row["action"] == "task.completed" for row in domain.audits[task.task_id])


def test_expired_lease_dead_letter_cancel_suspend_and_tenant_isolation(domain):
    task = approved(domain, "web", "read_file")
    domain.queue(task.task_id, TENANT, max_attempts=1, now=100)
    domain.claim(server_id="web", worker_id="web-worker", lease_seconds=10, now=100)
    assert domain.recover_expired(now=111) == {"retried": 0, "dead_lettered": 1}
    assert task.state == TaskState.DEAD_LETTER

    second = approved(domain, "web", "git_diff")
    domain.queue(second.task_id, TENANT)
    assert domain.suspend(second.task_id, TENANT).state == TaskState.SUSPENDED
    assert domain.resume(second.task_id, TENANT).state == TaskState.QUEUED
    assert domain.cancel(second.task_id, TENANT).state == TaskState.CANCELLED
    with pytest.raises(ControllerError, match="not found"):
        domain.get_task(second.task_id, "other-tenant")


def test_agent_capabilities_fail_closed(domain):
    approved(domain, "middleware", "odoo_read")
    approved(domain, "middleware", "n8n_workflow_read")
    approved(domain, "web", "run_unit_tests")
    for server, tool in (
        ("web", "odoo_read"),
        ("web", "n8n_workflow_read"),
        ("qwen", "git_status"),
        ("vici", "git_status"),
    ):
        with pytest.raises(ControllerError, match="server tool scope denied"):
            approved(domain, server, tool)


def test_business_capabilities_are_proposals_or_read_only(domain):
    prohibited = {"odoo_delete", "odoo_admin", "odoo_settings", "odoo_module_install",
                  "n8n_workflow_delete", "n8n_credentials", "n8n_users", "n8n_projects"}
    from app.core.controller import ALLOWED_TOOLS

    assert prohibited.isdisjoint(ALLOWED_TOOLS)
    assert all("proposal" in tool or tool.endswith(("_read", "_search", "_status", "_logs"))
               for tool in ALLOWED_TOOLS if tool.startswith(("odoo_", "n8n_")))
