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
        "schema_version": "codestra.production-canary.authorization.v1",
        "repository": "Codestra-SRL/codestra-middleware",
        "pr_number": 183,
        "release_sha": SHA,
        "image_digest": DIGEST,
        "vicidial_server": "65.21.67.207",
        "middleware_server": "65.109.65.169",
        "campaign": "TEST_SYN",
        "test_agent": "webtest001",
        "test_extension": "6101",
        "test_destination": "6000",
        "min_calls": 5,
        "max_calls": 10,
        "execution_window_start_utc": "2026-08-10T06:30:00Z",
        "execution_window_end_utc": "2026-08-10T07:00:00Z",
        "authorization_expiry_utc": "2026-08-10T07:30:00Z",
        "production_scope": ["controlled_internal_calls"],
        "production_flags": {"OUTBOX_PROCESSING_ENABLED": True},
        "rollback_sha": "c" * 40,
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
        ("vicidial_server", "203.0.113.1"),
        ("campaign", "CUSTOMERS"),
        ("test_destination", "18095550123"),
        ("min_calls", 4),
        ("max_calls", 11),
    ],
)
def test_identity_and_call_scope_changes_fail_closed(field, value) -> None:
    candidate = request()
    candidate[field] = value
    with pytest.raises(module.ValidationError):
        validate(candidate)


def test_unapproved_feature_flag_fails_closed() -> None:
    candidate = request()
    candidate["production_flags"] = {"LIVE_WRITES_ENABLED": True}
    with pytest.raises(module.ValidationError, match="allowlist"):
        validate(candidate)


def test_long_or_expired_window_fails_closed() -> None:
    candidate = request()
    candidate["execution_window_end_utc"] = "2026-08-10T08:00:00Z"
    candidate["authorization_expiry_utc"] = "2026-08-10T08:00:00Z"
    with pytest.raises(module.ValidationError, match="too broad"):
        validate(candidate)


def test_unknown_field_fails_closed() -> None:
    candidate = request()
    candidate["bypass"] = True
    with pytest.raises(module.ValidationError, match="fields"):
        validate(candidate)


def test_workflow_requires_separate_protected_owner_gates() -> None:
    workflow = (ROOT / ".github/workflows/production-canary-authorization.yml").read_text()
    assert "environment: production-release-owner" in workflow
    assert "environment: production-security-owner" in workflow
    assert "needs: [validate, release-owner, security-owner]" in workflow
    assert "id-token: write" in workflow
    assert "github.actor" in workflow
    assert "kazan555" in workflow
    assert "codestra/required-ci" in workflow
    assert "cosign sign-blob" in workflow
    assert "pull_request_target" not in workflow
