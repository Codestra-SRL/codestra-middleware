#!/usr/bin/env python3
"""Fail-closed semantic validation for security-owner request and decision JSON."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
BLOCKED = {
    "staging_deployment_gate", "production_deployment_gate",
    "production_activation_gate", "server_b_access_gate", "customer_data_gate",
    "telephony_access_gate", "recording_access_gate", "public_ingress_gate",
    "n8n_activation_gate", "n8n_binding_gate",
}


def fail(message: str) -> None:
    raise SystemExit(f"SECURITY_DECISION_VALIDATION_GATE=FAIL reason={message}")


def load(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("document_not_object")
    return value


def utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        fail("invalid_utc")
    if parsed.tzinfo is None:
        fail("timezone_required")
    return parsed.astimezone(timezone.utc)


def blocked(value: object) -> None:
    if not isinstance(value, dict) or set(value) != BLOCKED:
        fail("negative_authorization_set")
    if any(item != "blocked" for item in value.values()):
        fail("negative_authorization_not_blocked")


def validate_request(document: dict, manifest_path: str, pr_number: str, head: str) -> None:
    required = {"schema_version", "request_type", "repository", "pr_number", "pr_head_sha", "middleware_main_sha", "odoo_main_sha", "created_at_utc", "requested_expiration_utc", "approved_scope", "image_manifest_sha256", "image_digests", "vulnerability_findings", "compensating_controls", "odoo_isolation_evidence", "middleware_isolation_evidence", "limitations", "negative_authorizations", "revocation_conditions"}
    if set(document) != required:
        fail("request_fields")
    if document["schema_version"] != 1 or document["request_type"] != "security_owner_decision_request":
        fail("request_identity")
    if document["repository"] != "Codestra-SRL/codestra-middleware" or document["pr_number"] != int(pr_number) or int(pr_number) != 68:
        fail("repository_or_pr")
    if document["pr_head_sha"] != head or not SHA40.fullmatch(head):
        fail("pr_head")
    if document["approved_scope"] != "server_a_isolated_staging":
        fail("scope")
    for name in ("middleware_main_sha", "odoo_main_sha"):
        if not SHA40.fullmatch(document[name]):
            fail(name)
    manifest = Path(manifest_path).read_bytes()
    if hashlib.sha256(manifest).hexdigest() != document["image_manifest_sha256"]:
        fail("manifest_binding")
    if not isinstance(document["image_digests"], dict) or not document["image_digests"] or any(not DIGEST.fullmatch(v) for v in document["image_digests"].values()):
        fail("image_digests")
    for name in ("compensating_controls", "odoo_isolation_evidence", "middleware_isolation_evidence"):
        evidence = document[name]
        if set(evidence) != {"path", "sha256"} or not evidence["path"] or not SHA256.fullmatch(evidence["sha256"]):
            fail(name)
    created, expires = utc(document["created_at_utc"]), utc(document["requested_expiration_utc"])
    lifetime = (expires - created).total_seconds()
    if lifetime <= 0 or lifetime > 30 * 86400:
        fail("request_lifetime")
    if not isinstance(document["vulnerability_findings"], list) or not isinstance(document["revocation_conditions"], list) or not document["revocation_conditions"]:
        fail("findings_or_revocation")
    blocked(document["negative_authorizations"])


def validate_decision(document: dict) -> None:
    if document.get("decision_status") != "approved_for_staging_preparation":
        fail("decision_status")
    if document.get("repository") != "Codestra-SRL/codestra-middleware" or document.get("pr_number") != 68:
        fail("decision_subject")
    if document.get("approved_scope") != "server_a_isolated_staging":
        fail("decision_scope")
    if document.get("security_owner_approver_login") != "kazan555":
        fail("approver")
    if document.get("environment_name") != "security-owner-signing":
        fail("environment")
    if document.get("workflow_path") != ".github/workflows/security-owner-decision-sign.yml" or document.get("workflow_ref") != "refs/heads/main":
        fail("workflow_identity")
    for name in ("decision_request_sha256", "compensating_controls_sha256", "odoo_isolation_evidence_sha256", "middleware_isolation_evidence_sha256"):
        if not SHA256.fullmatch(str(document.get(name, ""))):
            fail(name)
    if not SHA40.fullmatch(str(document.get("pr_head_sha", ""))) or not SHA40.fullmatch(str(document.get("workflow_sha", ""))):
        fail("decision_sha")
    signed, expires = utc(document["signed_at_utc"]), utc(document["expires_at_utc"])
    if (expires - signed).total_seconds() <= 0 or (expires - signed).total_seconds() > 30 * 86400:
        fail("decision_lifetime")
    blocked(document["negative_authorizations"])


if __name__ == "__main__":
    if len(sys.argv) < 3:
        fail("usage")
    if sys.argv[1] == "request" and len(sys.argv) == 6:
        validate_request(load(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5])
    elif sys.argv[1] == "decision" and len(sys.argv) == 3:
        validate_decision(load(sys.argv[2]))
    else:
        fail("mode")
    print("SECURITY_DECISION_VALIDATION_GATE=PASS")
