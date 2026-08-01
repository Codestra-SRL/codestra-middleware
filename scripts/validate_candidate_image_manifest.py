#!/usr/bin/env python3
"""Fail-closed validation for the staging candidate image manifest."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn, cast

PLACEHOLDER = re.compile(r"(?:<[^>]+>|\b(?:unknown|placeholder|tbd|todo)\b)", re.IGNORECASE)


def fail(message: str) -> NoReturn:
    print(json.dumps({
        "candidate_manifest_schema_gate": "FAIL",
        "production_activation_gate": "blocked",
        "production_deployment_gate": "blocked",
        "reason": message,
        "security_owner_acceptance_present": False,
    }, sort_keys=True, separators=(",", ":")))
    raise SystemExit(1)


class StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        fail(f"invalid arguments: {message}")


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid {label}: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def validate(args: argparse.Namespace) -> None:
    schema = load_object(args.schema, "schema")
    manifest = load_object(args.manifest, "manifest")
    required = schema.get("required")
    properties = schema.get("properties")
    if schema.get("additionalProperties") is not False or not isinstance(required, list) or not isinstance(properties, dict):
        fail("schema must define required properties and reject additions")
    required = cast(list[str], required)
    properties = cast(dict[str, dict[str, Any]], properties)

    keys = set(manifest)
    missing = set(required) - keys
    additional = keys - set(properties)
    if missing:
        fail(f"missing fields: {','.join(sorted(missing))}")
    if additional:
        fail(f"unapproved fields: {','.join(sorted(additional))}")

    for name, rules in properties.items():
        value = manifest[name]
        if "const" in rules and value != rules["const"]:
            fail(f"{name} does not match schema constant")
        expected_type = rules.get("type")
        if expected_type == "string" and not isinstance(value, str):
            fail(f"{name} must be a string")
        if isinstance(value, str):
            if not value or PLACEHOLDER.search(value):
                fail(f"{name} contains a placeholder")
            pattern = rules.get("pattern")
            if pattern and re.search(pattern, value) is None:
                fail(f"{name} does not match schema pattern")

    exact = {
        "repository": args.expected_repository,
        "pr_number": args.expected_pr_number,
        "head_sha": args.expected_head_sha,
        "image_repository": args.expected_image_repository,
        "image_digest": args.expected_image_digest,
    }
    for name, expected in exact.items():
        if manifest[name] != expected:
            fail(f"{name} does not match the expected build identity")
    if "@sha256:" in manifest["image_repository"] or ":" in manifest["image_repository"].split("/")[-1]:
        fail("image_repository must not contain a tag or digest")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"sbom", "provenance", "trivy", "grype"}:
        fail("artifact bindings are incomplete")
    for name, artifact in cast(dict[str, Any], artifacts).items():
        if not isinstance(artifact, dict) or set(artifact) != {"reference", "sha256"}:
            fail(f"{name} artifact binding is malformed")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", str(artifact["reference"])):
            fail(f"{name} artifact reference is malformed")
        if not re.fullmatch(r"[0-9a-f]{64}", str(artifact["sha256"])):
            fail(f"{name} artifact digest is malformed")
    try:
        datetime.fromisoformat(manifest["created_utc"].removesuffix("Z") + "+00:00")
    except ValueError as exc:
        fail(f"created_utc is not RFC3339 UTC: {exc}")


def parse_args() -> argparse.Namespace:
    parser = StructuredArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-pr-number", type=int, required=True)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-image-repository", required=True)
    parser.add_argument("--expected-image-digest", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    validate(parse_args())
