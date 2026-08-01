from datetime import UTC, datetime

import pytest

from app.core.ai_jobs import AIActionDecision, AIJobControl, AIJobRequest, AIJobResult, TenantScope


def scope(tenant="tenant-a", company=1):
    return TenantScope(tenant_id=tenant, company_id=company, business_unit_key="sales", campaign_key="test")


def request(**overrides):
    values = {
        "job_id": "job-00000001", "event_id": "event-000001", "interaction_id": "interaction-1",
        "tenant_scope": scope(), "purpose": "post_call_summary",
        "object_reference": {"object_id": "synthetic", "content_hash": "sha256:" + "a" * 64},
        "allowed_operations": ["summarize"],
        "model_policy": {"remote_provider_allowed": False}, "retention_class": "interaction_short",
        "created_at": datetime(2026, 8, 1, 12, 0, tzinfo=UTC), "idempotency_key": "idempotency-key-0001",
    }
    values.update(overrides)
    return AIJobRequest(**values)


def result(**overrides):
    values = {
        "job_id": "job-00000001", "interaction_id": "interaction-1", "tenant_scope": scope(),
        "model_provider": "mock", "model_identifier": "mock-v1", "model_digest": "sha256:" + "b" * 64,
        "prompt_version": "v1", "policy_version": "v1", "input_hash": "c" * 64, "output_hash": "d" * 64,
        "redaction_status": "PASS", "confidence": 0.8, "result_payload": {}, "action_proposals": [],
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    return AIJobResult(**values)


def enabled():
    service = AIJobControl()
    service.enabled = service.submission_enabled = service.results_enabled = service.decisions_enabled = True
    return service


def test_default_off():
    with pytest.raises(PermissionError):
        AIJobControl().create(request())


def test_idempotency_and_conflicting_replay():
    service = enabled()
    first = service.create(request())
    assert service.create(request()) is first
    with pytest.raises(ValueError):
        service.create(request(purpose="post_call_quality"))


def test_cross_tenant_result_denied_without_mutation():
    service = enabled()
    state = service.create(request())
    with pytest.raises(LookupError):
        service.receive_result(result(tenant_scope=scope("tenant-b", 2)))
    assert state.result is None and state.status == "queued"


def test_result_binding_quarantines_and_reconciliation_counts_queue():
    service = enabled()
    service.create(request())
    with pytest.raises(PermissionError):
        service.receive_result(result(interaction_id="wrong"))
    assert len(service.quarantine) == 1 and service.reconcile() == 1


def test_human_decision_is_append_only_audited():
    service = enabled()
    service.create(request())
    service.receive_result(result())
    decision = AIActionDecision(
        proposal_id="proposal-1", job_id="job-00000001", tenant_scope=scope(), decision="approved",
        approver_id="synthetic-supervisor", approver_role="AI Supervisor Approver",
        proposal_hash="e" * 64, decided_at=datetime.now(UTC),
    )
    state = service.decide(decision)
    assert state.decisions == [decision]
    assert service.audit[-1]["event"] == "ai.action.decided"
