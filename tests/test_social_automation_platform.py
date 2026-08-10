from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.main import app
from app.platform.ai import (
    AIRequest,
    DisabledAIProvider,
    minimize_ai_input,
    optimization_recommendation,
)
from app.platform.domain import (
    CampaignState,
    InvalidCampaignTransition,
    LeadCategory,
    lead_identity_hash,
    normalize_analytics,
    provider_health_score,
    require_transition,
    score_lead,
    safe_location_reference,
    validate_media,
)
from app.platform.tracing import trace_context
from app.platform.workflows import canonical_workflow, detect_drift, security_findings
from app.tools.validate_n8n_workflows import validate_tree, validate_workflow

WORKFLOWS = Path("integrations/n8n/workflows")


def test_campaign_transition_state_machine_is_fail_closed():
    require_transition(CampaignState.DRAFT, CampaignState.CONTENT_GENERATING)
    require_transition(CampaignState.ACTIVE, CampaignState.PAUSED)
    with pytest.raises(InvalidCampaignTransition):
        require_transition(CampaignState.DRAFT, CampaignState.ACTIVE)
    with pytest.raises(InvalidCampaignTransition):
        require_transition(CampaignState.APPROVED, CampaignState.COMPLETED)


def test_lead_score_is_explainable_and_deterministic():
    signals = {
        "buying_intent": True,
        "company_match": True,
        "contact_available": True,
        "urgent": True,
    }
    first = score_lead(signals)
    second = score_lead(signals)
    assert first == second
    assert first.category == LeadCategory.HOT_LEAD
    assert first.score == sum(first.factors.values())
    assert "buying_intent" in first.factors


def test_lead_identity_hash_deduplicates_normalized_identifiers():
    assert lead_identity_hash(
        email=" Sales@Example.COM ", phone=None, profile=None
    ) == lead_identity_hash(email="sales@example.com", phone=None, profile=None)
    assert lead_identity_hash(email=None, phone=None, profile=None) is None


def test_analytics_never_fabricates_unsupported_metrics():
    result = normalize_analytics(
        {"impressions": 10, "likes": 2, "advertising_cost": 99, "views": "unknown"}
    )
    assert result["impressions"] == 10
    assert result["views"] is None
    assert "advertising_cost" not in result


def test_provider_health_keeps_components_and_never_fails_over():
    health = provider_health_score(
        reachable=True,
        authenticated=True,
        latency_ms=200,
        error_rate=0,
        poll_lag_seconds=5,
    )
    assert health.score == 100 and health.status == "HEALTHY"
    assert set(health.components) == {"api", "auth", "latency", "errors", "polling"}
    assert (
        provider_health_score(
            reachable=True,
            authenticated=False,
            latency_ms=1,
            error_rate=0,
            poll_lag_seconds=0,
        ).status
        == "AUTH_REQUIRED"
    )


def test_media_validation_blocks_executable_oversize_and_internal_reference():
    validate_media(
        content_type="image/png",
        filename="asset.png",
        size=100,
        checksum="a" * 64,
        maximum_bytes=1000,
    )
    with pytest.raises(ValueError, match="TYPE_UNSUPPORTED"):
        validate_media(
            content_type="application/x-executable",
            filename="asset.bin",
            size=1,
            checksum="a" * 64,
            maximum_bytes=1000,
        )
    with pytest.raises(ValueError, match="SIZE_INVALID"):
        validate_media(
            content_type="image/png",
            filename="asset.png",
            size=1001,
            checksum="a" * 64,
            maximum_bytes=1000,
        )
    with pytest.raises(ValueError, match="LOCATION_INVALID"):
        safe_location_reference("https://127.0.0.1/internal")


def test_ai_boundary_minimizes_secrets_and_requires_approval():
    assert minimize_ai_input(
        {"objective": "awareness", "token": "secret", "email": "person@example.com"}
    ) == {"objective": "awareness"}
    recommendation = optimization_recommendation(
        {"impressions": 100, "engagements": 2}, {"impressions": 100, "engagements": 5}
    )
    assert recommendation["action"] == "TEST_VARIANT"
    assert recommendation["requires_approval"] is True
    request = AIRequest("classification", "v1", {"text_hash": "abc"}, "corr")
    assert len(request.input_hash) == 64


@pytest.mark.asyncio
async def test_disabled_ai_provider_never_claims_success():
    with pytest.raises(RuntimeError, match="AI_PROVIDER_DISABLED"):
        await DisabledAIProvider().execute(
            AIRequest("classification", "v1", {}, "corr")
        )


def test_trace_context_propagates_valid_w3c_and_replaces_invalid():
    existing = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    assert trace_context(existing).traceparent == existing
    generated = trace_context("tampered")
    assert len(generated.trace_id) == 32 and generated.traceparent.startswith("00-")


def test_all_git_workflows_pass_policy_validator():
    assert validate_tree(WORKFLOWS) == []


def test_validator_blocks_direct_provider_unsafe_node_and_missing_paths():
    document = {
        "name": "unsafe",
        "nodes": [
            {
                "name": "shell",
                "type": "n8n-nodes-base.executeCommand",
                "parameters": {"url": "https://provider.invalid"},
            }
        ],
        "connections": {},
    }
    errors = validate_workflow(document, Path("unsafe.json"))
    assert any("unapproved node" in error for error in errors)
    assert any("dead-letter" in error for error in errors)
    assert any("audit/result" in error for error in errors)


def test_workflow_drift_and_security_audit_are_deterministic():
    path = WORKFLOWS / "security" / "CdstN8nSecurityAuditV1.json"
    expected = canonical_workflow(path)
    assert detect_drift(expected, json.loads(path.read_text())) is False
    changed = json.loads(path.read_text())
    changed["active"] = True
    assert detect_drift(expected, changed) is True
    assert security_findings(changed) == []


def test_source_defaults_are_fail_closed():
    values = Settings()
    assert values.social_publish_enabled is False
    assert values.social_production_canary_enabled is False
    assert values.social_odoo_write_enabled is False
    assert values.hootsuite_enabled is False
    assert values.ai_automatic_publish is False
    assert values.campaign_automatic_approval is False
    assert values.social_automatic_provider_failover_enabled is False
    assert values.social_automatic_dual_publish_enabled is False
    assert values.deadletter_automatic_replay is False
    assert values.social_global_kill_switch is True


def test_automatic_controls_are_rejected_even_if_requested():
    with pytest.raises(ValueError, match="automatic publishing"):
        Settings(ai_automatic_publish=True).validate_safety()
    with pytest.raises(ValueError, match="automatic provider failover"):
        Settings(social_automatic_provider_failover_enabled=True).validate_safety()


def test_openapi_has_provider_neutral_ops_campaign_and_health_contracts():
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/campaigns" in paths
    assert "/api/v1/campaigns/{campaign_id}/transitions" in paths
    assert "/api/v1/social/providers/health" in paths
    assert "/api/v1/ops/social/deadletters" in paths
    assert "/api/v1/leads/intelligence" in paths
    assert "/api/v1/social/analytics/normalize" in paths
    assert "/api/v1/ops/social/media" in paths
    assert "/api/v1/odoo/leads/dry-run" in paths
    assert "/api/v1/ops/social/deadletters/{job_id}/replay" in paths
    serialized = json.dumps(schema).casefold()
    assert "oauth_token" not in serialized
    assert "postiz_api_key" not in serialized
