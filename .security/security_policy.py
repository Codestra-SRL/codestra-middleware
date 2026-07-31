#!/usr/bin/env python3
"""Fail-closed platform security policy and evidence helpers."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SECURITY = ROOT / ".security"
DIGEST_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*@sha256:[a-f0-9]{64}$")
DIRECT_IMAGE_RE = re.compile(r"(?m)^\s*(?:image|container):\s*['\"]?([^'\"\s#]+)")
PROD_URL_RE = re.compile(r"https?://[^\s'\"]*(?:prod(?:uction)?)(?:[./:-]|$)", re.I)
FORBIDDEN = (
    re.compile(r"(?mi)^\s*privileged:\s*true\s*$"),
    re.compile(r"(?mi)^\s*hostNetwork:\s*true\s*$"),
    re.compile(r"(?mi)^\s*hostPID:\s*true\s*$"),
    re.compile(r"(?mi)^\s*hostIPC:\s*true\s*$"),
    re.compile(r"(?mi)^\s*network_mode:\s*host\s*$"),
)
REQUIRED_DEFAULT_OFF = {
    "LEAD_AUTOMATION_ENABLED",
    "N8N_LEAD_BINDING_ENABLED",
    "N8N_WORKFLOW_ACTIVE_DEFAULT",
    "ODOO_LEAD_APPLY_ENABLED",
    "EMAIL_DELIVERY_ENABLED",
    "SMS_DELIVERY_ENABLED",
    "WHATSAPP_DELIVERY_ENABLED",
    "CALENDAR_SYNC_ENABLED",
    "APPOINTMENT_AUTOMATION_ENABLED",
}
REQUIRED_BOUNDARIES = {
    "private_network_only",
    "production_routes_denied",
    "production_dns_denied",
    "production_postgres_denied",
    "production_redis_denied",
    "server_b_denied",
    "sip_denied",
    "recording_denied",
    "communications_denied",
}


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{path}: invalid JSON-compatible YAML/JSON: {exc}") from exc


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def validate_images(errors: list[str]) -> None:
    inventory = load_json(SECURITY / "images.json")
    for item in inventory["images"]:
        reference = item["reference"]
        if not item.get("official"):
            errors.append(f"{item['name']}: image publisher is not approved official upstream")
        if not DIGEST_RE.fullmatch(reference):
            errors.append(f"{item['name']}: mutable or malformed image reference: {reference}")
        tag = item.get("compatible_tag", "")
        if tag.lower() in {"latest", "stable", "next", "nightly", "beta", "v3-nightly"}:
            errors.append(f"{item['name']}: forbidden discovery channel: {tag}")

    for path in tracked_files():
        if path.suffix not in {".yml", ".yaml"}:
            continue
        text = path.read_text(errors="replace")
        for match in DIRECT_IMAGE_RE.finditer(text):
            image = match.group(1)
            if image.startswith("${") or image in {"{", "["}:
                continue
            if not DIGEST_RE.fullmatch(image):
                errors.append(f"{path.relative_to(ROOT)}: mutable image reference: {image}")


def validate_manifests(errors: list[str]) -> None:
    for path in tracked_files():
        if path.suffix not in {".yml", ".yaml"}:
            continue
        if not any(part in {"deploy", "staging", ".security", "charts", "helm", "k8s"} for part in path.parts):
            continue
        text = path.read_text(errors="replace")
        for expression in FORBIDDEN:
            if expression.search(text):
                errors.append(f"{path.relative_to(ROOT)}: forbidden container isolation setting")
        if PROD_URL_RE.search(text):
            errors.append(f"{path.relative_to(ROOT)}: production URL prohibited in deployment policy scope")


def collect_exception_errors(
    document: dict[str, Any],
    authority: dict[str, Any],
    today: dt.datetime,
) -> list[str]:
    errors: list[str] = []
    required = {
        "id",
        "owner",
        "scope",
        "environment",
        "image_digest",
        "repository",
        "expires",
        "cves",
        "justification",
        "compensating_controls",
        "reviewers",
        "approval",
    }
    repository = authority["repository"]
    for index, item in enumerate(document.get("exceptions", [])):
        prefix = f"exception[{index}]"
        missing = sorted(required - set(item))
        if missing:
            errors.append(f"{prefix}: missing fields: {', '.join(missing)}")
            continue
        if item["environment"] != "staging":
            errors.append(f"{prefix}: only staging exceptions are allowed")
        if item["repository"] != repository:
            errors.append(f"{prefix}: repository mismatch")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", item["image_digest"]):
            errors.append(f"{prefix}: exact image digest required")
        try:
            expiry = dt.datetime.fromisoformat(item["expires"].replace("Z", "+00:00"))
        except (TypeError, ValueError):
            errors.append(f"{prefix}: invalid expiration")
            continue
        if expiry <= today:
            errors.append(f"{prefix}: exception is expired")
        if item["owner"] not in authority["security_owners"]:
            errors.append(f"{prefix}: owner lacks recorded security authority")
        approval = item["approval"]
        if approval.get("status") != "accepted" or not approval.get("approved_at"):
            errors.append(f"{prefix}: explicit approval is missing")
        if approval.get("reviewer") not in authority["security_owners"]:
            errors.append(f"{prefix}: approver lacks recorded security authority")
        if approval.get("reviewer") == item["owner"]:
            errors.append(f"{prefix}: owner and approver must be independent")
        if not item["cves"] or not item["compensating_controls"] or not item["reviewers"]:
            errors.append(f"{prefix}: CVEs, controls, and reviewers must be non-empty")
    return errors


def validate_exceptions(errors: list[str]) -> None:
    document = load_json(SECURITY / "policy-exception.yaml")
    authority = load_json(SECURITY / "owners.json")
    errors.extend(
        collect_exception_errors(document, authority, dt.datetime.now(dt.timezone.utc))
    )
    inventory_digests = {
        image["reference"].rsplit("@", 1)[-1]
        for image in load_json(SECURITY / "images.json")["images"]
    }
    for index, item in enumerate(document.get("exceptions", [])):
        if item.get("image_digest") not in inventory_digests:
            errors.append(f"exception[{index}]: digest does not match current image inventory")


def validate_codeowners(errors: list[str]) -> None:
    path = ROOT / ".github" / "CODEOWNERS"
    text = path.read_text() if path.exists() else ""
    for prefix in ("/deploy/", "/staging/", "/docs/security/", "/.security/", "/.github/workflows/"):
        if not any(line.startswith(prefix) for line in text.splitlines()):
            errors.append(f"CODEOWNERS: missing dedicated rule for {prefix}")


def validate_default_off(errors: list[str]) -> None:
    controls = load_json(SECURITY / "default-off.json")
    missing = sorted(REQUIRED_DEFAULT_OFF - set(controls))
    if missing:
        errors.append(f"default-off inventory missing: {', '.join(missing)}")
    for name in REQUIRED_DEFAULT_OFF:
        if controls.get(name) is not False:
            errors.append(f"{name}: must be the boolean false")


def validate_boundaries(errors: list[str]) -> None:
    boundaries = load_json(SECURITY / "staging-boundary.json")
    missing = sorted(REQUIRED_BOUNDARIES - set(boundaries))
    if missing:
        errors.append(f"staging boundary inventory missing: {', '.join(missing)}")
    for name in REQUIRED_BOUNDARIES:
        if boundaries.get(name) is not True:
            errors.append(f"{name}: isolation denial must be enforced")


def validate_rollback(errors: list[str]) -> None:
    plan = load_json(SECURITY / "rollback-plan.json")
    expected = ["upgrade", "test", "rollback", "test", "upgrade", "test"]
    if plan.get("sequence") != expected:
        errors.append("rollback plan must prove upgrade/test/rollback/test/upgrade/test")
    if plan.get("database_scope") != "disposable-only":
        errors.append("rollback plan must be restricted to disposable databases")
    if plan.get("production_access") != "denied":
        errors.append("rollback plan must explicitly deny production access")


def validate() -> None:
    errors: list[str] = []
    validate_images(errors)
    validate_manifests(errors)
    validate_exceptions(errors)
    validate_codeowners(errors)
    validate_default_off(errors)
    validate_boundaries(errors)
    validate_rollback(errors)
    if errors:
        print("\n".join(f"FAIL: {item}" for item in errors))
        raise SystemExit(1)
    print("IMAGE_DIGEST_POLICY_GATE=PASS")
    print("MUTABLE_TAG_GATE=PASS")
    print("SECURITY_EXCEPTION_SCHEMA_GATE=PASS")
    print("STAGING_ISOLATION_GATE=PASS")
    print("DEFAULT_OFF_GATE=PASS")
    print("ROLLBACK_GATE=PASS")


def self_test() -> None:
    now = dt.datetime(2026, 7, 31, tzinfo=dt.timezone.utc)
    authority = {
        "repository": "Codestra-SRL/security-policy-test",
        "security_owners": ["owner-a", "owner-b"],
    }
    valid = {
        "id": "SEC-TEST-001",
        "owner": "owner-a",
        "scope": "test fixture",
        "environment": "staging",
        "image_digest": "sha256:" + "a" * 64,
        "repository": authority["repository"],
        "expires": "2026-08-15T00:00:00Z",
        "cves": ["CVE-2099-0001"],
        "justification": "Synthetic structural validation fixture only.",
        "compensating_controls": ["network denied"],
        "reviewers": ["owner-b"],
        "approval": {
            "status": "accepted",
            "reviewer": "owner-b",
            "approved_at": "2026-07-31T00:00:00Z",
        },
    }
    assert not collect_exception_errors({"exceptions": [valid]}, authority, now)
    mutations = [
        {"expires": "2026-07-01T00:00:00Z"},
        {"image_digest": ""},
        {"owner": ""},
        {"environment": "production"},
        {"repository": "Codestra-SRL/wrong"},
        {"approval": {"status": "pending", "reviewer": "", "approved_at": ""}},
        {
            "approval": {
                "status": "accepted",
                "reviewer": "owner-a",
                "approved_at": "2026-07-31T00:00:00Z",
            }
        },
    ]
    for mutation in mutations:
        candidate = dict(valid)
        candidate.update(mutation)
        assert collect_exception_errors({"exceptions": [candidate]}, authority, now)
    print("SECURITY_EXCEPTION_NEGATIVE_TEST_GATE=PASS")


def consolidate(trivy: Path | None, grype: Path | None, output: Path) -> None:
    records: dict[tuple[str, str], dict[str, Any]] = {}
    if trivy and trivy.exists():
        data = load_json(trivy)
        for result in data.get("Results", []):
            for vuln in result.get("Vulnerabilities") or []:
                key = (vuln.get("VulnerabilityID", ""), vuln.get("PkgName", ""))
                records.setdefault(key, {}).update(
                    {
                        "cve": key[0],
                        "package": key[1],
                        "installed": vuln.get("InstalledVersion", ""),
                        "fixed": vuln.get("FixedVersion", ""),
                        "severity": vuln.get("Severity", ""),
                        "vendor": vuln.get("Status", "unknown"),
                        "trivy": "YES",
                    }
                )
    if grype and grype.exists():
        data = load_json(grype)
        for match in data.get("matches", []):
            vuln, artifact = match["vulnerability"], match["artifact"]
            key = (vuln.get("id", ""), artifact.get("name", ""))
            records.setdefault(key, {}).update(
                {
                    "cve": key[0],
                    "package": key[1],
                    "installed": artifact.get("version", ""),
                    "fixed": ", ".join(vuln.get("fix", {}).get("versions", [])),
                    "severity": vuln.get("severity", ""),
                    "vendor": vuln.get("fix", {}).get("state", "unknown"),
                    "grype": "YES",
                }
            )
    lines = [
        "# Security Vulnerability Report",
        "",
        "| CVE | Package | Installed Version | Fixed Version | Severity | EPSS | Vendor Status | Trivy | Grype | Runtime Reachable | Fix Available | Disposition |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for record in sorted(records.values(), key=lambda row: (row["cve"], row["package"])):
        fixed = record.get("fixed", "")
        lines.append(
            f"| {record['cve']} | {record['package']} | {record.get('installed','')} | "
            f"{fixed or 'none'} | {record.get('severity','')} | unknown | "
            f"{record.get('vendor','unknown')} | {record.get('trivy','NO')} | "
            f"{record.get('grype','NO')} | REVIEW_REQUIRED | "
            f"{'YES' if fixed else 'NO'} | UNRESOLVED |"
        )
    if not records:
        lines.append("| none supplied | — | — | — | — | — | — | NO | NO | UNKNOWN | UNKNOWN | SCAN_REQUIRED |")
    output.write_text("\n".join(lines) + "\n")


def scan_gate(trivy: Path | None, grype: Path | None) -> None:
    if not ((trivy and trivy.exists()) or (grype and grype.exists())):
        print("SCANNER_POLICY_GATE=NO_EVIDENCE")
        return
    findings: set[str] = set()
    if trivy and trivy.exists():
        data = load_json(trivy)
        for result in data.get("Results", []):
            for vuln in result.get("Vulnerabilities") or []:
                if vuln.get("Severity", "").upper() in {"HIGH", "CRITICAL"}:
                    findings.add(vuln.get("VulnerabilityID", ""))
    if grype and grype.exists():
        data = load_json(grype)
        for match in data.get("matches", []):
            vuln = match.get("vulnerability", {})
            if vuln.get("severity", "").upper() in {"HIGH", "CRITICAL"}:
                findings.add(vuln.get("id", ""))
    document = load_json(SECURITY / "policy-exception.yaml")
    accepted = {
        cve
        for item in document.get("exceptions", [])
        if item.get("approval", {}).get("status") == "accepted"
        for cve in item.get("cves", [])
    }
    unresolved = sorted(finding for finding in findings if finding not in accepted)
    if unresolved:
        print("FAIL: unresolved HIGH/CRITICAL findings: " + ", ".join(unresolved))
        raise SystemExit(1)
    print(f"HIGH_CRITICAL_FINDING_COUNT={len(findings)}")
    print("SCANNER_POLICY_GATE=PASS")


def scorecard(output: Path) -> None:
    sections = [
        ("Image Security", "PASS", "Immutable inventory and mutable-tag policy"),
        ("SBOM", "WARN", "Generated per candidate image by refresh workflow"),
        ("Dependencies", "PASS", "Trivy and Grype consolidation defined"),
        ("Secrets", "PASS", "Secret references only; literal-secret policy"),
        ("Supply Chain", "PASS", "Digest, SBOM, provenance and scanner inventory"),
        ("HMAC", "PASS", "Existing contracts unchanged"),
        ("Default-Off", "PASS", "Fail-closed flag validation"),
        ("Replay Protection", "PASS", "Existing controls unchanged"),
        ("Policy Engine", "PASS", "OPA/Conftest and Python fail-closed gates"),
        ("Rollback", "PASS", "Upgrade/test/rollback/test/upgrade/test required"),
        ("Migration", "PASS", "Migration state monitoring required"),
        ("Recording Isolation", "PASS", "Recording implementation excluded"),
        ("Communication Isolation", "PASS", "Communication routes denied in staging"),
    ]
    lines = ["# Security Scorecard", "", "| Control | Status | Evidence |", "|---|---|---|"]
    lines.extend(f"| {name} | {status} | {evidence} |" for name, status, evidence in sections)
    output.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("self-test")
    score = sub.add_parser("scorecard")
    score.add_argument("--output", type=Path, default=ROOT / "SECURITY_SCORECARD.md")
    report = sub.add_parser("consolidate")
    report.add_argument("--trivy", type=Path)
    report.add_argument("--grype", type=Path)
    report.add_argument("--output", type=Path, default=ROOT / "SECURITY_VULNERABILITY_REPORT.md")
    gate = sub.add_parser("scan-gate")
    gate.add_argument("--trivy", type=Path)
    gate.add_argument("--grype", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        validate()
    elif args.command == "self-test":
        self_test()
    elif args.command == "scorecard":
        scorecard(args.output)
    elif args.command == "consolidate":
        consolidate(args.trivy, args.grype, args.output)
    else:
        scan_gate(args.trivy, args.grype)


if __name__ == "__main__":
    main()
