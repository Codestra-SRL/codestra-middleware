from fastapi import HTTPException

from app.api.v1.allocations import (
    AllocationBundleRequest,
    IdentityReservationRequest,
    _require_provider_checks,
)
from app.workers import delivery, outbox


def test_identity_allocator_requires_explicit_provider_evidence():
    request = IdentityReservationRequest(
        resource_type="AGENT_PUBLIC_ID",
        candidate_public_ids=["agent-candidate-a", "agent-candidate-b"],
        environment="STAGING",
        organization_public_id="org",
        business_unit_public_id="bu",
        purpose="acceptance",
        idempotency_key="allocation-idempotency-001",
        provider_checks={"middleware": True, "odoo": True},
    )
    assert request.candidate_public_ids[0] != request.candidate_public_ids[1]
    _require_provider_checks(request.provider_checks, {"middleware", "odoo"})


def test_identity_allocator_rejects_incomplete_provider_evidence():
    try:
        _require_provider_checks({"middleware": True}, {"middleware", "odoo"})
    except HTTPException as error:
        assert error.status_code == 503
    else:
        raise AssertionError("allocation must fail closed without Odoo evidence")


def test_test_resource_bundle_is_dynamic_and_not_an_implicit_fixture():
    request = AllocationBundleRequest(
        environment="STAGING",
        organization_public_id="org",
        business_unit_public_id="bu",
        purpose="acceptance",
        idempotency_key="bundle-idempotency-001",
        provider_checks={
            provider: True
            for provider in ("middleware", "odoo", "redis", "keycloak", "vicidial", "asterisk", "n8n")
        },
        identity_reservations=[IdentityReservationRequest(
            resource_type="LEAD_PUBLIC_ID",
            candidate_public_ids=["lead-candidate-a"],
            environment="STAGING",
            organization_public_id="org",
            business_unit_public_id="bu",
            purpose="acceptance",
            idempotency_key="lead-idempotency-001",
            provider_checks={"middleware": True, "odoo": True},
        )],
    )
    assert request.identity_reservations[0].candidate_public_ids == ["lead-candidate-a"]
    assert "6110" not in str(request.model_dump())


def test_recovery_uses_skip_locked_and_clears_expired_leases():
    assert "FOR UPDATE SKIP LOCKED" in str(outbox.CLAIM_SQL)
    assert "FOR UPDATE OF d SKIP LOCKED" in str(delivery.CLAIM)
    assert "lease expired" in str(outbox.RECOVER_SQL)
    assert "lease_expires_at<=:now" in str(delivery.RECOVER)


def test_recovery_has_bounded_retry_and_authorized_replay_primitives():
    assert "dead_letter" in str(outbox.FAIL_SQL)
    assert "attempts" in str(outbox.FAIL_SQL)
    assert "status='dead_letter'" in str(outbox.REPLAY_SQL)
    assert "replay_count=replay_count + 1" in str(outbox.REPLAY_SQL)
