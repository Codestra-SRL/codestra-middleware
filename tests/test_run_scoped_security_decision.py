from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/generate_security_owner_decision.py"
VALIDATOR = ROOT / "scripts/validate_security_owner_decision.py"
SCHEMA = ROOT / "schemas/security-owner-decision-request.v1.schema.json"
AUTHORITY = ROOT / "security/governance/security-owner-authority.json"
HEAD = "a" * 40
DIGEST = "sha256:" + "b" * 64


def fixture(tmp_path: Path) -> dict[str, Path]:
    files = {name: tmp_path / name for name in ["manifest.json", "matrix.csv", "sbom.json", "trivy.json", "grype.json", "provenance.json"]}
    for name, path in files.items():
        if name != "matrix.csv":
            path.write_text(json.dumps({"name": name}))
    with files["matrix.csv"].open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["vulnerability_id", "package", "installed_version", "package_path", "severity", "fixed_versions", "scanners"])
        writer.writeheader()
        for path in ["/usr/local/bin/python3.12", "/usr/local/lib/libpython3.12.so.1.0"]:
            writer.writerow({"vulnerability_id": "CVE-2026-1", "package": "python", "installed_version": "3.12.13", "package_path": path, "severity": "HIGH", "fixed_versions": "3.13.14", "scanners": "Grype"})
    return files


def command(tmp_path: Path) -> tuple[list[str], dict[str, Path], Path, str]:
    files = fixture(tmp_path)
    output = tmp_path / "decision.json"
    authority_sha = hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    common = [
        "--source-sha", HEAD, "--image-digest", DIGEST, "--run-id", "12345",
        "--run-attempt", "2", "--authority", str(AUTHORITY),
        "--authority-sha256", authority_sha, "--authority-run-id", "9876",
        "--authority-artifact", "security-owner-authority-9876-1",
        "--manifest", str(files["manifest.json"]), "--matrix", str(files["matrix.csv"]),
        "--sbom", str(files["sbom.json"]), "--trivy", str(files["trivy.json"]),
        "--grype", str(files["grype.json"]), "--provenance", str(files["provenance.json"]),
    ]
    subprocess.run(["python3", str(GENERATOR), *common, "--output", str(output)], check=True)
    return common, files, output, authority_sha


def validate(common: list[str], output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["python3", str(VALIDATOR), "--decision", str(output), "--schema", str(SCHEMA), *common], check=False, capture_output=True, text=True)


def test_exact_same_run_decision_passes(tmp_path: Path) -> None:
    common, _, output, _ = command(tmp_path)
    assert validate(common, output).returncode == 0


@pytest.mark.parametrize("field", ["repository", "pr_number", "pr_head_sha", "image_digest", "build_run_id", "build_run_attempt", "matrix_sha256", "sbom_sha256", "provenance_sha256", "authority_reference"])
def test_missing_or_wrong_binding_fails(tmp_path: Path, field: str) -> None:
    common, _, output, _ = command(tmp_path)
    document = json.loads(output.read_text())
    if field in {"repository", "pr_number"}:
        document.pop(field)
    else:
        document[field] = "wrong"
    output.write_text(json.dumps(document))
    assert validate(common, output).returncode != 0


def test_cross_run_and_local_only_substitution_fail(tmp_path: Path) -> None:
    common, _, output, _ = command(tmp_path)
    wrong = common.copy()
    wrong[wrong.index("--run-id") + 1] = "12346"
    assert validate(wrong, output).returncode != 0
    wrong = common.copy()
    wrong[wrong.index("--authority-artifact") + 1] = "local-only-decision"
    assert validate(wrong, output).returncode != 0


def test_decision_generation_and_validation_precede_both_uploads() -> None:
    workflow = (ROOT / ".github/workflows/staging-candidate-build-sign.yml").read_text()
    evidence_validation = workflow.index("- name: Validate complete candidate evidence")
    decision_generation = workflow.index("- name: Generate and validate exact run-scoped Security Owner decision")
    evidence_upload = workflow.index("- name: Upload exact run-scoped candidate evidence")
    decision_upload = workflow.index("- name: Upload exact run-scoped Security Owner decision")
    assert evidence_validation < decision_generation < evidence_upload < decision_upload
    assert "decision-SHA256SUMS" in workflow[decision_generation:decision_upload]
    assert "test \"${EVIDENCE_RUN_ID}\" = \"${DECISION_RUN_ID}\"" in workflow
    assert "pr68-security-owner-decision-${{ inputs.source_sha }}-${{ github.run_id }}-${{ github.run_attempt }}" in workflow
