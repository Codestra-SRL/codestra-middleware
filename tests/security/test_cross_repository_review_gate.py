from __future__ import annotations

import importlib.util
import json
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/security/evaluate-cross-repository-review.py"
SPEC = importlib.util.spec_from_file_location("cross_repository_gate", PATH)
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

NOW = datetime(2026, 8, 1, 16, 0, tzinfo=timezone.utc)  # noqa: UP017
SHAS = ("a" * 40, "b" * 40, "c" * 40)


def decision() -> dict:
    repositories = []
    for index, repository in enumerate(gate.EXPECTED_REPOSITORIES):
        sha = SHAS[index]
        repositories.append({
            "repository": repository,
            "sha": sha,
            "pr_number": index + 1,
            "pr_current_head_sha": sha,
            "commit_exists": True,
            "ci_head_sha": sha,
            "ci_conclusion": "success",
            "ci_run_id": index + 10,
            "ci_run_url": f"https://github.com/{repository}/actions/runs/{index + 10}",
            "commit_authors": ["author"],
        })
    return {
        "schema_version": "1.0.0",
        "final_status": gate.APPROVED,
        "scope": "server_a_isolated_staging",
        "repositories": repositories,
        "reviewer": {"login": "reviewer", "authenticated": True, "authorized": True},
        "review_package_creator": "creator",
        "reviewed_at_utc": "2026-08-01T15:00:00Z",
        "expires_at_utc": "2026-08-02T15:00:00Z",
        "revoked": False,
        "signature_required": True,
        "restrictions": deepcopy(gate.RESTRICTIONS),
    }


def validate(value: dict | None = None, **kwargs: object) -> None:
    gate.validate_decision(value or decision(), signature_verified=True, now=NOW, **kwargs)


def test_exact_valid_combined_decision_passes() -> None:
    validate()


@pytest.mark.parametrize("sha", ["a" * 7, "A" * 40, "g" * 40, "a" * 41])
def test_non_exact_lowercase_sha_fails_closed(sha: str) -> None:
    value = decision()
    value["repositories"][0]["sha"] = sha
    value["repositories"][0]["pr_current_head_sha"] = sha
    value["repositories"][0]["ci_head_sha"] = sha
    with pytest.raises(gate.GateError):
        validate(value)


def test_duplicate_repository_fails_closed() -> None:
    value = decision()
    value["repositories"][2]["repository"] = value["repositories"][1]["repository"]
    with pytest.raises(gate.GateError):
        validate(value)


@pytest.mark.parametrize("field,bad", [
    ("commit_exists", False), ("ci_conclusion", "failure"),
    ("pr_current_head_sha", "d" * 40), ("ci_head_sha", "d" * 40),
])
def test_repository_proof_failures_are_rejected(field: str, bad: object) -> None:
    value = decision()
    value["repositories"][0][field] = bad
    with pytest.raises(gate.GateError):
        validate(value)


@pytest.mark.parametrize("field,bad", [("authenticated", False), ("authorized", False), ("login", "")])
def test_unknown_or_unauthorized_reviewer_is_rejected(field: str, bad: object) -> None:
    value = decision()
    value["reviewer"][field] = bad
    with pytest.raises(gate.GateError):
        validate(value)


def test_reviewer_author_or_package_creator_overlap_is_rejected() -> None:
    author = decision()
    author["repositories"][1]["commit_authors"].append("reviewer")
    creator = decision()
    creator["review_package_creator"] = "reviewer"
    for value in (author, creator):
        with pytest.raises(gate.GateError):
            validate(value)


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(revoked=True),
    lambda value: value.update(expires_at_utc="2026-08-01T15:30:00Z"),
    lambda value: value["restrictions"].update(canary_allowed=True),
])
def test_revoked_stale_or_expanded_decision_is_rejected(mutation) -> None:
    value = decision()
    mutation(value)
    with pytest.raises(gate.GateError):
        validate(value)


def test_signature_and_fixture_fail_closed() -> None:
    with pytest.raises(gate.GateError):
        gate.validate_decision(decision(), signature_verified=False, now=NOW)
    with pytest.raises(gate.GateError):
        validate(fixture=True)


def test_missing_and_unknown_fields_fail_closed() -> None:
    missing = decision()
    missing.pop("reviewer")
    unknown = decision()
    unknown["bypass"] = True
    for value in (missing, unknown):
        with pytest.raises(gate.GateError):
            validate(value)


def test_only_success_output_is_narrow_inactive_import_status() -> None:
    script = PATH.read_text(encoding="utf-8")
    assert 'APPROVED = "APPROVED_FOR_INACTIVE_STAGING_IMPORT"' in script
    assert "READY_FOR_DEPLOYMENT" not in script
    assert "bypass" not in script.lower()


def test_structured_results_never_expand_restricted_scope() -> None:
    approved = gate.result_document(gate.APPROVED, "verified")
    blocked = gate.result_document(gate.BLOCKED, "invalid")
    assert approved["inactive_staging_import_allowed"] is True
    assert blocked["inactive_staging_import_allowed"] is False
    for result in (approved, blocked):
        assert result["workflow_activation_allowed"] is False
        assert result["canary_allowed"] is False
        assert result["persistent_deployment_allowed"] is False
        assert result["production_allowed"] is False
        assert result["server_b_allowed"] is False
        assert result["customer_data_allowed"] is False
        assert result["real_calls_allowed"] is False
        assert result["email_sms_allowed"] is False


def test_invalid_signature_emits_one_unambiguous_json_result() -> None:
    completed = subprocess.run(
        [str(PATH), "--decision", "/dev/null", "--bundle", "/dev/null"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    assert completed.stderr == ""
    lines = completed.stdout.splitlines()
    assert len(lines) == 1
    result = json.loads(lines[0])
    assert result["final_status"] == gate.BLOCKED
    assert result["inactive_staging_import_allowed"] is False


def test_signature_verifier_has_exact_identity_and_no_regex() -> None:
    script = PATH.read_text()
    assert "cross-repository-review-sign.yml@refs/heads/main" in script
    assert "certificate-identity-regexp" not in script
    assert "certificate-oidc-issuer-regexp" not in script
    assert "subprocess.run" in script
