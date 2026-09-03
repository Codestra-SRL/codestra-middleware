#!/usr/bin/env python3
"""Fail-closed evaluator for the three-repository inactive-staging import gate."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

SHA = re.compile(r"^[0-9a-f]{40}$")
EXPECTED_REPOSITORIES = (
    "Codestra-SRL/codestra-middleware",
    "Codestra-SRL/codestra-odoo-addons",
    "Codestra-SRL/codestra-n8n-workflows",
)
APPROVED = "APPROVED_FOR_INACTIVE_STAGING_IMPORT"
BLOCKED = "BLOCKED_GOVERNANCE_EVIDENCE_INVALID"
RESTRICTIONS = {
    "n8n_import_allowed": True,
    "n8n_activation_allowed": False,
    "canary_allowed": False,
    "persistent_deployment_allowed": False,
    "production_allowed": False,
    "server_b_allowed": False,
    "customer_data_allowed": False,
    "real_calls_allowed": False,
    "email_sms_allowed": False,
}
TOP_LEVEL_KEYS = {
    "schema_version", "final_status", "scope", "repositories", "reviewer",
    "review_package_creator", "reviewed_at_utc", "expires_at_utc", "revoked",
    "signature_required", "restrictions",
}
REPOSITORY_KEYS = {
    "repository", "sha", "pr_number", "pr_current_head_sha", "commit_exists",
    "ci_head_sha", "ci_conclusion", "ci_run_id", "ci_run_url", "commit_authors",
}
REVIEWER_KEYS = {"login", "authenticated", "authorized"}


class GateError(ValueError):
    pass


def result_document(status: str, reason: str) -> dict[str, Any]:
    return {
        "canary_allowed": False,
        "customer_data_allowed": False,
        "email_sms_allowed": False,
        "final_status": status,
        "inactive_staging_import_allowed": status == APPROVED,
        "persistent_deployment_allowed": False,
        "production_allowed": False,
        "real_calls_allowed": False,
        "reason": reason,
        "server_b_allowed": False,
        "workflow_activation_allowed": False,
    }


def emit_result(status: str, reason: str) -> None:
    print(json.dumps(result_document(status, reason), separators=(",", ":"), sort_keys=True))


class GateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        emit_result(BLOCKED, f"invalid evaluator invocation: {message}")
        raise SystemExit(2)


def load_object(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError("decision cannot be loaded") from exc
    if not isinstance(value, dict):
        raise GateError("decision must be a JSON object")
    return value


def verify_signature(decision: str | Path, bundle: str | Path) -> None:
    command = [
        "cosign", "verify-blob", "--bundle", str(bundle),
        "--certificate-identity",
        "https://github.com/Codestra-SRL/codestra-middleware/.github/workflows/cross-repository-review-sign.yml@refs/heads/main",
        "--certificate-oidc-issuer", "https://token.actions.githubusercontent.com",
        str(decision),
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GateError("detached signature verification failed") from exc


def exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise GateError(f"{label} fields mismatch")


def parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise GateError(f"{label} must be an unambiguous UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")  # noqa: FURB162
    except ValueError as exc:
        raise GateError(f"invalid {label}") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):  # noqa: UP017
        raise GateError(f"{label} must be UTC")
    return parsed


def validate_decision(
    decision: dict[str, Any], *, signature_verified: bool, fixture: bool = False,
    now: datetime | None = None,
) -> None:
    if fixture:
        raise GateError("synthetic fixtures cannot authorize a real gate")
    exact_keys(decision, TOP_LEVEL_KEYS, "decision")
    if decision["schema_version"] != "1.0.0":
        raise GateError("unsupported schema version")
    if decision["final_status"] != APPROVED:
        raise GateError("decision is not an inactive-staging import approval")
    if decision["scope"] != "server_a_isolated_staging":
        raise GateError("scope mismatch")
    if decision["revoked"] is not False:
        raise GateError("decision is revoked or revocation is ambiguous")
    if decision["signature_required"] is not True or not signature_verified:
        raise GateError("required detached signature was not verified")
    if decision["restrictions"] != RESTRICTIONS:
        raise GateError("restricted operations are not explicitly blocked")

    reviewed = parse_utc(decision["reviewed_at_utc"], "reviewed_at_utc")
    expires = parse_utc(decision["expires_at_utc"], "expires_at_utc")
    current = now or datetime.now(timezone.utc)  # noqa: UP017
    if reviewed > current or expires <= current or expires <= reviewed:
        raise GateError("decision is stale, not yet valid, or has invalid expiry")

    reviewer = decision["reviewer"]
    if not isinstance(reviewer, dict):
        raise GateError("reviewer must be an object")
    exact_keys(reviewer, REVIEWER_KEYS, "reviewer")
    login = reviewer["login"]
    if not isinstance(login, str) or not login or reviewer["authenticated"] is not True or reviewer["authorized"] is not True:
        raise GateError("reviewer identity is unknown or unauthorized")
    creator = decision["review_package_creator"]
    if not isinstance(creator, str) or not creator or creator.casefold() == login.casefold():
        raise GateError("reviewer created the review package")

    repositories = decision["repositories"]
    if not isinstance(repositories, list) or len(repositories) != 3:
        raise GateError("exactly three repository bindings are required")
    names: list[str] = []
    for index, binding in enumerate(repositories):
        if not isinstance(binding, dict):
            raise GateError(f"repository binding {index} must be an object")
        exact_keys(binding, REPOSITORY_KEYS, f"repository binding {index}")
        repository = binding["repository"]
        names.append(repository)
        sha = binding["sha"]
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise GateError(f"invalid exact SHA for {repository}")
        if binding["commit_exists"] is not True:
            raise GateError(f"commit existence not proven for {repository}")
        if binding["pr_current_head_sha"] != sha:
            raise GateError(f"PR advanced after review for {repository}")
        if binding["ci_head_sha"] != sha or binding["ci_conclusion"] != "success":
            raise GateError(f"exact-head CI missing or unsuccessful for {repository}")
        if not isinstance(binding["pr_number"], int) or binding["pr_number"] < 1:
            raise GateError(f"invalid PR number for {repository}")
        if not isinstance(binding["ci_run_id"], int) or binding["ci_run_id"] < 1:
            raise GateError(f"invalid CI run for {repository}")
        if not isinstance(binding["ci_run_url"], str) or not binding["ci_run_url"].startswith("https://github.com/"):
            raise GateError(f"invalid CI URL for {repository}")
        authors = binding["commit_authors"]
        if not isinstance(authors, list) or not authors or any(not isinstance(author, str) or not author for author in authors):
            raise GateError(f"commit authors are missing for {repository}")
        if login.casefold() in {author.casefold() for author in authors}:
            raise GateError(f"reviewer authored or co-authored {repository}")
    if tuple(names) != EXPECTED_REPOSITORIES:
        raise GateError("repository bindings must be the exact unique ordered set")


def main() -> None:
    parser = GateArgumentParser()
    parser.add_argument("--decision", required=True)
    parser.add_argument("--bundle", required=True)
    args = parser.parse_args()
    try:
        verify_signature(args.decision, args.bundle)
        validate_decision(load_object(args.decision), signature_verified=True)
    except (GateError, OSError) as exc:
        emit_result(BLOCKED, str(exc))
        raise SystemExit(1) from exc
    emit_result(APPROVED, "exact-SHA independent review and signature verified")


if __name__ == "__main__":
    main()
