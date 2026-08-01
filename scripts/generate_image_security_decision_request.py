#!/usr/bin/env python3
"""Create a digest-bound unsigned Security Owner decision request."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, NoReturn


class DecisionRequestError(ValueError):
    pass


class StructuredArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        fail(f"invalid arguments: {message}")


SHA = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionRequestError(f"malformed {label} JSON") from exc
    if not isinstance(value, dict):
        raise DecisionRequestError(f"{label} must be an object")
    return value


def digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise DecisionRequestError(f"evidence cannot be read: {path}") from exc


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def atomic_write(path: Path, content: bytes) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
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
        raise DecisionRequestError("decision request could not be written atomically") from exc


def require_artifact_binding(manifest: dict[str, Any], name: str, path: Path) -> None:
    try:
        binding = manifest["artifacts"][name]
    except (KeyError, TypeError) as exc:
        raise DecisionRequestError(f"missing {name} manifest binding") from exc
    if binding != {"reference": path.name, "sha256": digest(path)}:
        raise DecisionRequestError(f"{name} digest or reference mismatch")


def scanner_findings(trivy: dict[str, Any], grype: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(trivy.get("Results"), list) or not isinstance(grype.get("matches"), list):
        raise DecisionRequestError("scanner JSON does not contain findings arrays")
    findings: list[dict[str, Any]] = []
    counts: dict[str, Counter[str]] = {"trivy": Counter(), "grype": Counter()}
    for result in trivy["Results"]:
        if not isinstance(result, dict):
            raise DecisionRequestError("malformed Trivy result")
        vulnerabilities = result.get("Vulnerabilities") or []
        if not isinstance(vulnerabilities, list):
            raise DecisionRequestError("malformed Trivy vulnerabilities")
        for item in vulnerabilities:
            if not isinstance(item, dict):
                raise DecisionRequestError("malformed Trivy finding")
            severity = str(item.get("Severity", "")).upper()
            if severity not in {"HIGH", "CRITICAL"}:
                continue
            if not all(isinstance(item.get(field), str) and item[field] for field in ("VulnerabilityID", "PkgName", "InstalledVersion")):
                raise DecisionRequestError("malformed Trivy finding identity")
            counts["trivy"][severity] += 1
            findings.append({
                "cve": item.get("VulnerabilityID"), "fix_availability": bool(item.get("FixedVersion")),
                "fixed_version": item.get("FixedVersion") or None,
                "installed_version": item.get("InstalledVersion"), "package": item.get("PkgName"),
                "remediation_status": "unresolved", "runtime_relevance": "requires_security_owner_assessment",
                "scanner": "trivy", "severity": severity,
            })
    for match in grype["matches"]:
        if not isinstance(match, dict):
            raise DecisionRequestError("malformed Grype finding")
        vulnerability, artifact = match.get("vulnerability"), match.get("artifact")
        if not isinstance(vulnerability, dict) or not isinstance(artifact, dict):
            raise DecisionRequestError("malformed Grype finding identity")
        severity = str(vulnerability.get("severity", "")).upper()
        if severity not in {"HIGH", "CRITICAL"}:
            continue
        if not all((isinstance(vulnerability.get("id"), str) and vulnerability["id"],
                    isinstance(artifact.get("name"), str) and artifact["name"],
                    isinstance(artifact.get("version"), str) and artifact["version"])):
            raise DecisionRequestError("malformed Grype finding identity")
        fixes = (vulnerability.get("fix") or {}).get("versions") or []
        if not isinstance(fixes, list):
            raise DecisionRequestError("malformed Grype fix versions")
        counts["grype"][severity] += 1
        findings.append({
            "cve": vulnerability.get("id"), "fix_availability": bool(fixes),
            "fixed_version": fixes, "installed_version": artifact.get("version"),
            "package": artifact.get("name"), "remediation_status": "unresolved",
            "runtime_relevance": "requires_security_owner_assessment", "scanner": "grype",
            "severity": severity,
        })
    findings.sort(key=lambda row: (str(row["scanner"]), str(row["severity"]), str(row["cve"]), str(row["package"])))
    return {
        "trivy": {"critical": counts["trivy"]["CRITICAL"], "high": counts["trivy"]["HIGH"]},
        "grype": {"critical": counts["grype"]["CRITICAL"], "high": counts["grype"]["HIGH"]},
    }, findings


def build_request(manifest_path: Path, sbom_path: Path, provenance_path: Path,
                  trivy_path: Path, grype_path: Path) -> dict[str, Any]:
    manifest = load_object(manifest_path, "candidate manifest")
    if manifest.get("repository") != "Codestra-SRL/codestra-middleware":
        raise DecisionRequestError("candidate repository mismatch")
    if not isinstance(manifest.get("pr_number"), int) or manifest["pr_number"] < 1:
        raise DecisionRequestError("candidate PR number is invalid")
    if not SHA.fullmatch(str(manifest.get("head_sha", ""))):
        raise DecisionRequestError("candidate head SHA is invalid")
    if manifest.get("image_repository") != "ghcr.io/codestra-srl/codestra-middleware":
        raise DecisionRequestError("candidate image repository mismatch")
    if not IMAGE_DIGEST.fullmatch(str(manifest.get("image_digest", ""))):
        raise DecisionRequestError("candidate image digest is invalid")
    if manifest.get("production_deployment_gate") != "blocked" or manifest.get("production_activation_gate") != "blocked":
        raise DecisionRequestError("candidate production gates must remain blocked")
    sbom, provenance = load_object(sbom_path, "SBOM"), load_object(provenance_path, "provenance")
    trivy, grype = load_object(trivy_path, "Trivy"), load_object(grype_path, "Grype")
    paths = {"sbom": sbom_path, "provenance": provenance_path, "trivy": trivy_path, "grype": grype_path}
    for name, path in paths.items():
        require_artifact_binding(manifest, name, path)
    image_repository, image_digest, head_sha = manifest["image_repository"], manifest["image_digest"], manifest["head_sha"]
    image = f"{image_repository}@{image_digest}"
    component = (sbom.get("metadata") or {}).get("component") or {}
    if component.get("name") != image_repository or component.get("version") != image_digest:
        raise DecisionRequestError("SBOM image digest mismatch")
    try:
        subject = provenance["subject"][0]
        source = provenance["predicate"]["buildDefinition"]["externalParameters"]["source_sha"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DecisionRequestError("provenance binding is malformed") from exc
    if subject.get("name") != image_repository or subject.get("digest", {}).get("sha256") != image_digest.removeprefix("sha256:") or source != head_sha:
        raise DecisionRequestError("provenance digest or source mismatch")
    if trivy.get("ArtifactName") != image:
        raise DecisionRequestError("Trivy image digest mismatch")
    if ((grype.get("source") or {}).get("target") or {}).get("userInput") != image:
        raise DecisionRequestError("Grype image digest mismatch")
    counts, findings = scanner_findings(trivy, grype)
    evidence = {
        name: {"reference": path.name, "sha256": digest(path)}
        for name, path in sorted(paths.items())
    }
    return {
        "$schema": "https://codestra.internal/schemas/image-security-decision.v1.json",
        "approved_scope": None,
        "compensating_control_template": ["private-network-only", "external-delivery-disabled", "synthetic-data-only"],
        "customer_data_gate": "blocked", "detached_signature_reference": None,
        "evidence": evidence, "expires_utc": None, "head_sha": head_sha,
        "image_digest": image_digest, "image_repository": image_repository,
        "issued_utc": None, "pr_number": manifest["pr_number"],
        "production_activation_gate": "blocked", "production_deployment_gate": "blocked",
        "proposed_staging_scope": "server_a_isolated_staging",
        "repository": manifest["repository"],
        "revocation_condition_template": ["source-sha-change", "image-digest-change", "new-critical-finding", "scope-change"],
        "scanner_counts": counts, "schema_version": "1.0", "security_owner": None,
        "security_owner_acceptance_present": False, "security_owner_authority_reference": None,
        "server_b_access_gate": "blocked", "signer_identity": None,
        "status": "pending_security_owner_review", "unresolved_findings": findings,
    }


def fail(message: str) -> NoReturn:
    print(json.dumps({"production_activation_gate": "blocked", "production_deployment_gate": "blocked", "reason": message, "security_decision_request_gate": "FAIL", "security_owner_acceptance_present": False}, sort_keys=True, separators=(",", ":")))
    raise SystemExit(1)


def main() -> None:
    parser = StructuredArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--trivy", type=Path, required=True)
    parser.add_argument("--grype", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = build_request(args.manifest, args.sbom, args.provenance, args.trivy, args.grype)
        atomic_write(args.output, canonical_bytes(request))
    except (DecisionRequestError, KeyError, TypeError) as exc:
        args.output.unlink(missing_ok=True)
        fail(str(exc))
    print(json.dumps({"output": str(args.output), "security_decision_request_gate": "PASS", "security_owner_acceptance_present": False}, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
