from datetime import datetime, timezone

import pytest

from app.core.social_postly import SocialControlPlane, SocialError, SocialState

NOW = datetime(2026, 8, 2, 12, tzinfo=timezone.utc)  # noqa: UP017


def request() -> dict:
    return {
        "organization_id": "ORG-CODESTRA",
        "workspace_id": "WS-TEST",
        "campaign_id": "CMP-TEST",
        "content_job_id": "JOB-1",
        "content_version": 1,
        "integration_ids": ["INT-CODESTRA-TEST"],
        "scheduled_at": "2026-08-03T12:00:00Z",
        "preferred_language": "en",
        "correlation_id": "COR-MOCK-E2E",
    }


def approved(control: SocialControlPlane):
    job = control.create(request())
    control.accept_n8n_proposal(
        job.content_job_id,
        {
            "content_job_id": job.content_job_id,
            "content_version": 1,
            "language": "en",
            "caption": "Codestra private integration test.",
            "status": "proposal_only",
        },
    )
    return control.approve(
        job.content_job_id,
        approval_id="APR-1",
        approved_by="USR-TEST",
        content_version=1,
    )


def test_odoo_middleware_n8n_middleware_mock_postly_and_analytics():
    control = SocialControlPlane(now=lambda: NOW)
    job = approved(control)
    assert job.state == SocialState.APPROVED
    first = control.schedule(job.content_job_id)
    second = control.schedule(job.content_job_id)
    assert first.state == SocialState.SCHEDULED
    assert first.provider_group_id == second.provider_group_id
    assert control.adapter.calls == 1
    assert control.analytics(job.content_job_id) == {
        "impressions": 0,
        "reactions": 0,
        "comments": 0,
        "shares": 0,
    }
    assert [item.action for item in job.audit] == [
        "n8n_generation_queued",
        "n8n_proposal_received",
        "human_approved",
        "provider_command_queued",
        "provider_scheduled",
    ]


def test_approval_and_stale_n8n_are_enforced():
    control = SocialControlPlane(now=lambda: NOW)
    job = control.create(request())
    with pytest.raises(SocialError, match="immutable approval"):
        control.schedule(job.content_job_id)
    with pytest.raises(SocialError, match="binding conflict"):
        control.accept_n8n_proposal(
            job.content_job_id,
            {
                "content_job_id": "JOB-1",
                "content_version": 2,
                "status": "proposal_only",
                "caption": "stale",
            },
        )


def test_temporary_failure_retries_once_without_duplicate():
    control = SocialControlPlane(now=lambda: NOW)
    job = approved(control)
    control.adapter.fail_next = "temporary"
    assert control.schedule(job.content_job_id).state == SocialState.FAILED
    assert job.next_attempt_at is not None
    assert control.retry(job.content_job_id).state == SocialState.SCHEDULED
    assert control.adapter.calls == 2
    assert len(control.adapter.posts) == 1


def test_uncertain_write_reconciles_without_retrying_write():
    control = SocialControlPlane(now=lambda: NOW)
    job = approved(control)
    control.adapter.fail_next = "timeout_after_write"
    assert (
        control.schedule(job.content_job_id).state
        == SocialState.RECONCILIATION_REQUIRED
    )
    calls = control.adapter.calls
    assert control.reconcile(job.content_job_id).state == SocialState.SCHEDULED
    assert control.adapter.calls == calls
    assert len(control.adapter.posts) == 1


def test_reconciliation_is_bound_to_workspace_and_idempotency_claim():
    control = SocialControlPlane(now=lambda: NOW)
    first = approved(control)
    control.adapter.fail_next = "timeout_after_write"
    control.schedule(first.content_job_id)

    other = request()
    other.update(
        {
            "workspace_id": "WS-OTHER",
            "content_job_id": "JOB-OTHER",
            "correlation_id": "COR-OTHER",
        }
    )
    second = control.create(other)
    control.accept_n8n_proposal(
        second.content_job_id,
        {
            "content_job_id": second.content_job_id,
            "content_version": 1,
            "language": "en",
            "caption": "other workspace",
            "status": "proposal_only",
        },
    )
    control.approve(
        second.content_job_id,
        approval_id="APR-OTHER",
        approved_by="USR-OTHER",
        content_version=1,
    )
    assert control.reconcile(second.content_job_id).state == SocialState.APPROVED
    assert control.reconcile(first.content_job_id).state == SocialState.SCHEDULED
