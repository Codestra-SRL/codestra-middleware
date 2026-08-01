from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/generate_image_security_decision_request.py"
SPEC = importlib.util.spec_from_file_location("decision_request", PATH)
assert SPEC and SPEC.loader
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)

REPOSITORY = "ghcr.io/codestra-srl/codestra-middleware"
DIGEST = "sha256:" + "b" * 64
HEAD = "a" * 40


def write(path: Path, value: object) -> Path:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    return path


def evidence(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    sbom = write(tmp_path / "candidate.cdx.json", {"metadata": {"component": {"name": REPOSITORY, "version": DIGEST}}})
    provenance = write(tmp_path / "provenance.json", {
        "subject": [{"name": REPOSITORY, "digest": {"sha256": DIGEST.removeprefix("sha256:")}}],
        "predicate": {"buildDefinition": {"externalParameters": {"source_sha": HEAD}}},
    })
    trivy = write(tmp_path / "trivy.json", {"ArtifactName": f"{REPOSITORY}@{DIGEST}", "Results": [{"Vulnerabilities": [{"VulnerabilityID": "CVE-1", "Severity": "HIGH", "PkgName": "pkg", "InstalledVersion": "1", "FixedVersion": "2"}]}]})
    grype = write(tmp_path / "grype.json", {"source": {"target": {"userInput": f"{REPOSITORY}@{DIGEST}"}}, "matches": [{"vulnerability": {"id": "CVE-2", "severity": "Critical", "fix": {"versions": []}}, "artifact": {"name": "pkg2", "version": "1"}}]})
    paths = {"sbom": sbom, "provenance": provenance, "trivy": trivy, "grype": grype}
    manifest = write(tmp_path / "candidate-image-manifest.json", {
        "repository": "Codestra-SRL/codestra-middleware", "pr_number": 68,
        "head_sha": HEAD, "image_repository": REPOSITORY, "image_digest": DIGEST,
        "production_deployment_gate": "blocked", "production_activation_gate": "blocked",
        "artifacts": {name: {"reference": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for name, path in paths.items()},
    })
    return manifest, sbom, provenance, trivy, grype


def build(tmp_path: Path) -> dict:
    return helper.build_request(*evidence(tmp_path))


def test_pending_unsigned_request_is_fail_closed(tmp_path: Path) -> None:
    request = build(tmp_path)
    assert request["status"] == "pending_security_owner_review"
    assert request["security_owner_acceptance_present"] is False
    for field in ("approved_scope", "security_owner", "security_owner_authority_reference", "signer_identity", "issued_utc", "expires_utc", "detached_signature_reference"):
        assert request[field] is None
    for gate in ("production_deployment_gate", "production_activation_gate", "server_b_access_gate", "customer_data_gate"):
        assert request[gate] == "blocked"


@pytest.mark.parametrize("name", ["sbom", "provenance", "trivy", "grype"])
def test_evidence_digest_mismatch_fails(tmp_path: Path, name: str) -> None:
    paths = evidence(tmp_path)
    manifest = json.loads(paths[0].read_text())
    manifest["artifacts"][name]["sha256"] = "0" * 64
    write(paths[0], manifest)
    with pytest.raises(helper.DecisionRequestError, match=name):
        helper.build_request(*paths)


@pytest.mark.parametrize(("index", "mutation", "label"), [
    (1, lambda value: value["metadata"]["component"].update(version="sha256:" + "c" * 64), "SBOM"),
    (2, lambda value: value["predicate"]["buildDefinition"]["externalParameters"].update(source_sha="c" * 40), "provenance"),
    (3, lambda value: value.update(ArtifactName=f"{REPOSITORY}@sha256:{'c' * 64}"), "Trivy"),
    (4, lambda value: value["source"]["target"].update(userInput=f"{REPOSITORY}@sha256:{'c' * 64}"), "Grype"),
])
def test_internal_evidence_binding_mismatch_fails(tmp_path: Path, index: int, mutation, label: str) -> None:
    paths = evidence(tmp_path)
    value = json.loads(paths[index].read_text())
    mutation(value)
    write(paths[index], value)
    manifest = json.loads(paths[0].read_text())
    key = ("sbom", "provenance", "trivy", "grype")[index - 1]
    manifest["artifacts"][key]["sha256"] = hashlib.sha256(paths[index].read_bytes()).hexdigest()
    write(paths[0], manifest)
    with pytest.raises(helper.DecisionRequestError, match=label):
        helper.build_request(*paths)


@pytest.mark.parametrize("index", [3, 4])
def test_malformed_scanner_json_fails(tmp_path: Path, index: int) -> None:
    paths = evidence(tmp_path)
    paths[index].write_text("not-json", encoding="utf-8")
    with pytest.raises(helper.DecisionRequestError, match="malformed"):
        helper.build_request(*paths)


def test_production_gate_change_fails(tmp_path: Path) -> None:
    paths = evidence(tmp_path)
    manifest = json.loads(paths[0].read_text())
    manifest["production_deployment_gate"] = "allowed"
    write(paths[0], manifest)
    with pytest.raises(helper.DecisionRequestError, match="blocked"):
        helper.build_request(*paths)


def test_canonical_request_is_stable(tmp_path: Path) -> None:
    assert helper.canonical_bytes(build(tmp_path)) == helper.canonical_bytes(build(tmp_path))


def test_decision_request_atomic_write_removes_partial_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "image-security-decision.request.json"
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("synthetic")))
    with pytest.raises(helper.DecisionRequestError):
        helper.atomic_write(output, b"{}\n")
    assert not output.exists()
    assert not list(tmp_path.glob(".image-security-decision.request.json.*"))


def test_cli_failure_emits_one_fail_closed_json(tmp_path: Path) -> None:
    output = tmp_path / "image-security-decision.request.json"
    completed = subprocess.run(
        [sys.executable, str(PATH), "--output", str(output)],
        text=True, capture_output=True, check=False,
    )
    assert completed.returncode != 0
    assert completed.stderr == ""
    lines = completed.stdout.splitlines()
    assert len(lines) == 1
    status = json.loads(lines[0])
    assert status["security_decision_request_gate"] == "FAIL"
    assert status["security_owner_acceptance_present"] is False
    assert status["production_deployment_gate"] == "blocked"
    assert status["production_activation_gate"] == "blocked"
    assert not output.exists()
