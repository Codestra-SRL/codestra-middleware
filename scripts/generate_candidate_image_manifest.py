#!/usr/bin/env python3
"""Generate an exact-head, exact-digest candidate manifest atomically."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

EXPECTED_REPOSITORY = "Codestra-SRL/codestra-middleware"
ALLOWED_IMAGE_REPOSITORIES = {"ghcr.io/codestra-srl/codestra-middleware"}
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
POSITIVE_INTEGER = re.compile(r"^[1-9][0-9]*$")
REQUIRED_ENV = (
    "CANDIDATE_REPOSITORY", "CANDIDATE_PR_NUMBER", "CANDIDATE_HEAD_SHA",
    "CANDIDATE_IMAGE_REPOSITORY", "CANDIDATE_IMAGE_DIGEST",
    "CANDIDATE_WORKFLOW_RUN_ID", "CANDIDATE_WORKFLOW_RUN_ATTEMPT",
    "CANDIDATE_CREATED_UTC", "GITHUB_API_URL", "GH_TOKEN",
)


class ManifestError(ValueError):
    pass


class StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        fail(f"invalid arguments: {message}")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ManifestError(f"artifact cannot be read: {path}") from exc


def required_environment() -> dict[str, str]:
    values = {name: os.environ.get(name, "") for name in REQUIRED_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ManifestError("missing required environment: " + ",".join(missing))
    return values


def live_pr_head(api_url: str, token: str, repository: str, pr_number: int) -> str:
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/repos/{repository}/pulls/{pr_number}",
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = json.load(response)
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ManifestError("live PR head could not be verified") from exc
    try:
        state, head = body["state"], body["head"]["sha"]
    except (KeyError, TypeError) as exc:
        raise ManifestError("GitHub PR response is malformed") from exc
    if state != "open" or not isinstance(head, str) or not SHA.fullmatch(head):
        raise ManifestError("live PR is not open or has an invalid head")
    return head


def validate_identity(values: dict[str, str]) -> tuple[int, str]:
    if values["CANDIDATE_REPOSITORY"] != EXPECTED_REPOSITORY:
        raise ManifestError("candidate repository is not authoritative")
    if not POSITIVE_INTEGER.fullmatch(values["CANDIDATE_PR_NUMBER"]):
        raise ManifestError("candidate PR number must be a positive integer")
    if not SHA.fullmatch(values["CANDIDATE_HEAD_SHA"]):
        raise ManifestError("candidate head must be an exact lowercase SHA")
    if values["CANDIDATE_IMAGE_REPOSITORY"] not in ALLOWED_IMAGE_REPOSITORIES:
        raise ManifestError("candidate image repository is not allowlisted")
    if values["GITHUB_API_URL"] != "https://api.github.com":
        raise ManifestError("GitHub API context is not authoritative")
    if not DIGEST.fullmatch(values["CANDIDATE_IMAGE_DIGEST"]):
        raise ManifestError("candidate image digest is malformed")
    for name in ("CANDIDATE_WORKFLOW_RUN_ID", "CANDIDATE_WORKFLOW_RUN_ATTEMPT"):
        if not POSITIVE_INTEGER.fullmatch(values[name]):
            raise ManifestError(f"{name} must be a positive integer")
    try:
        created = datetime.fromisoformat(values["CANDIDATE_CREATED_UTC"].removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ManifestError("candidate creation timestamp is invalid") from exc
    offset = created.utcoffset()
    if not values["CANDIDATE_CREATED_UTC"].endswith("Z") or offset is None or offset.total_seconds() != 0:
        raise ManifestError("candidate creation timestamp must be UTC")
    return int(values["CANDIDATE_PR_NUMBER"]), values["CANDIDATE_HEAD_SHA"]


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise ManifestError("candidate manifest could not be written atomically") from exc


def build_manifest(values: dict[str, str], artifacts: dict[str, Path]) -> dict[str, Any]:
    pr_number, head_sha = validate_identity(values)
    if live_pr_head(values["GITHUB_API_URL"], values["GH_TOKEN"], values["CANDIDATE_REPOSITORY"], pr_number) != head_sha:
        raise ManifestError("live PR head does not match candidate head")
    artifact_records = {
        name: {"reference": path.name, "sha256": sha256_file(path)}
        for name, path in sorted(artifacts.items())
    }
    return {
        "$schema": "https://codestra.internal/schemas/candidate-image-manifest.v1.json",
        "artifacts": artifact_records,
        "candidate_scope": "server_a_isolated_staging_candidate",
        "created_utc": values["CANDIDATE_CREATED_UTC"],
        "head_sha": head_sha,
        "image_digest": values["CANDIDATE_IMAGE_DIGEST"],
        "image_repository": values["CANDIDATE_IMAGE_REPOSITORY"],
        "pr_number": pr_number,
        "production_activation_gate": "blocked",
        "production_deployment_gate": "blocked",
        "repository": values["CANDIDATE_REPOSITORY"],
        "schema_version": "1.0",
        "workflow_run_attempt": values["CANDIDATE_WORKFLOW_RUN_ATTEMPT"],
        "workflow_run_id": values["CANDIDATE_WORKFLOW_RUN_ID"],
    }


def fail(message: str) -> NoReturn:
    print(json.dumps({"candidate_manifest_gate": "FAIL", "reason": message}, sort_keys=True, separators=(",", ":")))
    raise SystemExit(1)


def main() -> None:
    parser = StructuredArgumentParser()
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--trivy", type=Path, required=True)
    parser.add_argument("--grype", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = build_manifest(required_environment(), {
            "sbom": args.sbom, "provenance": args.provenance,
            "trivy": args.trivy, "grype": args.grype,
        })
        atomic_write(args.output, canonical_bytes(manifest))
    except ManifestError as exc:
        args.output.unlink(missing_ok=True)
        fail(str(exc))
    print(json.dumps({"candidate_manifest_gate": "PASS", "output": str(args.output)}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
