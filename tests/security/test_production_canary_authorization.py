from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/security/validate-production-canary-authorization.py"
SPEC = importlib.util.spec_from_file_location("production_canary", PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
NOW = datetime(2026, 8, 10, 6, 0, tzinfo=timezone.utc)


def request() -> dict:
    return {
        "schema_version": "codestra.production-canary.authorization.v2",
        "middleware_repository": "Codestra-SRL/codestra-middleware",
        "pr_number": 183,
        "release_sha": SHA,
        "image_digest": DIGEST,
        "deployment_environment": "production",
        "test_campaign": "TEST_SYN",
        "test_agent": "webtest001",
        "test_extension": "6101",
        "test_lead": 41,
        "test_list": 9001,
        "test_destination": "6000",
        "test_disposition": "CALLBK",
        "maximum_call_count": 1,
        "allowed_call_type": "internal_test_only",
        "customer_data_allowed": False,
        "pstn_allowed": False,
        "valid_from": "2026-08-10T06:30:00Z",
        "valid_until": "2026-08-10T07:00:00Z",
        "rollback_authority": "operations-owner",
        "authorized_flags": {"OUTBOX_PROCESSING_ENABLED": True},
    }


def validate(candidate: dict) -> None:
    module.validate(
        candidate,
        repository="Codestra-SRL/codestra-middleware",
        pr_number=183,
        release_sha=SHA,
        image_digest=DIGEST,
        now=NOW,
    )


def test_exact_bounded_request_passes() -> None:
    validate(request())


@pytest.mark.parametrize(
    "field,value",
    [
        ("release_sha", "d" * 40),
        ("image_digest", "sha256:" + "d" * 64),
        ("test_campaign", "CUSTOMERS"),
        ("test_destination", "18095550123"),
        ("test_disposition", "SALE"),
        ("maximum_call_count", 2),
        ("allowed_call_type", "external"),
        ("customer_data_allowed", True),
        ("pstn_allowed", True),
    ],
)
def test_identity_and_call_scope_changes_fail_closed(field, value) -> None:
    candidate = request()
    candidate[field] = value
    with pytest.raises(module.ValidationError):
        validate(candidate)


def test_unapproved_feature_flag_fails_closed() -> None:
    candidate = request()
    candidate["authorized_flags"] = {"LIVE_WRITES_ENABLED": True}
    with pytest.raises(module.ValidationError, match="allowlist"):
        validate(candidate)


def test_long_or_expired_window_fails_closed() -> None:
    candidate = request()
    candidate["valid_until"] = "2026-08-10T08:00:01Z"
    with pytest.raises(module.ValidationError, match="too broad"):
        validate(candidate)


def test_unknown_field_fails_closed() -> None:
    candidate = request()
    candidate["bypass"] = True
    with pytest.raises(module.ValidationError, match="fields"):
        validate(candidate)


def test_expired_authorization_fails_closed() -> None:
    candidate = request()
    candidate["valid_from"] = "2026-08-10T05:00:00Z"
    candidate["valid_until"] = "2026-08-10T05:30:00Z"
    with pytest.raises(module.ValidationError, match="execution window"):
        validate(candidate)


def test_workflow_requires_separate_protected_owner_gates() -> None:
    workflow = (ROOT / ".github/workflows/production-canary-authorization.yml").read_text()
    assert "environment: production-release-owner" in workflow
    assert "environment: production-security-owner" in workflow
    assert "needs: [validate, release-owner, security-owner]" in workflow
    assert "id-token: write" in workflow
    assert "github.actor" in workflow
    assert "CODESTRA_RELEASE_OWNER_LOGIN" in workflow
    assert "CODESTRA_SECURITY_OWNER_LOGIN" in workflow
    assert "codestra/required-ci" in workflow
    assert "cosign sign-blob" in workflow
    assert "pull_request_target" not in workflow


def test_workflow_accepts_only_merged_exact_release_and_detached_request() -> None:
    workflow = (ROOT / ".github/workflows/production-canary-authorization.yml").read_text()
    assert 'test "$(jq -r .merged_at pr.json)" != "null"' in workflow
    assert 'test "$(jq -r .head.sha pr.json)" = "${SHA}"' in workflow
    assert 'git merge-base --is-ancestor "${SHA}" "${GITHUB_SHA}"' in workflow
    assert "request_base64" in workflow
    assert "contents/${PATH_INPUT}?ref=${SHA}" not in workflow
    assert 'test "${{ github.actor }}" != "${{ vars.CODESTRA_RELEASE_OWNER_LOGIN }}"' in workflow
    assert 'test "${{ github.actor }}" != "${{ vars.CODESTRA_SECURITY_OWNER_LOGIN }}"' in workflow
