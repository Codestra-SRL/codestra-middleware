from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/generate_candidate_image_manifest.py"
SPEC = importlib.util.spec_from_file_location("candidate_manifest", PATH)
assert SPEC and SPEC.loader
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)

HEAD = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64


def values() -> dict[str, str]:
    return {
        "CANDIDATE_REPOSITORY": "Codestra-SRL/codestra-middleware",
        "CANDIDATE_PR_NUMBER": "68", "CANDIDATE_HEAD_SHA": HEAD,
        "CANDIDATE_IMAGE_REPOSITORY": "ghcr.io/codestra-srl/codestra-middleware",
        "CANDIDATE_IMAGE_DIGEST": IMAGE_DIGEST, "CANDIDATE_WORKFLOW_RUN_ID": "123",
        "CANDIDATE_WORKFLOW_RUN_ATTEMPT": "1", "CANDIDATE_CREATED_UTC": "2026-08-01T20:00:00Z",
        "GITHUB_API_URL": "https://api.github.com", "GH_TOKEN": "synthetic-test-token",
    }


def artifacts(tmp_path: Path) -> dict[str, Path]:
    result = {}
    for name in ("sbom", "provenance", "trivy", "grype"):
        result[name] = tmp_path / f"{name}.json"
        result[name].write_text(f'{{"name":"{name}"}}\n', encoding="utf-8")
    return result


def build(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, candidate: dict[str, str] | None = None) -> dict:
    monkeypatch.setattr(generator, "live_pr_head", lambda *_: (candidate or values())["CANDIDATE_HEAD_SHA"])
    return generator.build_manifest(candidate or values(), artifacts(tmp_path))


@pytest.mark.parametrize("name", generator.REQUIRED_ENV)
def test_missing_required_input_fails(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    for key, value in values().items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(name)
    with pytest.raises(generator.ManifestError):
        generator.required_environment()


@pytest.mark.parametrize(("name", "value"), [
    ("CANDIDATE_REPOSITORY", "wrong/repository"),
    ("CANDIDATE_PR_NUMBER", "0"), ("CANDIDATE_PR_NUMBER", "not-a-number"),
    ("CANDIDATE_HEAD_SHA", "a" * 7), ("CANDIDATE_HEAD_SHA", "A" * 40),
    ("CANDIDATE_IMAGE_DIGEST", ""), ("CANDIDATE_IMAGE_DIGEST", "sha256:abc"),
    ("CANDIDATE_IMAGE_REPOSITORY", "ghcr.io/codestra-srl/not-allowed"),
])
def test_invalid_identity_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, value: str) -> None:
    candidate = values()
    candidate[name] = value
    with pytest.raises(generator.ManifestError):
        build(monkeypatch, tmp_path, candidate)


def test_live_pr_head_mismatch_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(generator, "live_pr_head", lambda *_: "c" * 40)
    with pytest.raises(generator.ManifestError, match="live PR head"):
        generator.build_manifest(values(), artifacts(tmp_path))


def test_canonical_output_is_stable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    first = build(monkeypatch, tmp_path)
    second = build(monkeypatch, tmp_path)
    assert generator.canonical_bytes(first) == generator.canonical_bytes(second)
    assert first["production_deployment_gate"] == "blocked"
    assert first["production_activation_gate"] == "blocked"


def test_atomic_write_removes_partial_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "candidate-image-manifest.json"
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("synthetic")))
    with pytest.raises(generator.ManifestError):
        generator.atomic_write(output, b"{}\n")
    assert not output.exists()
    assert not list(tmp_path.glob(".candidate-image-manifest.json.*"))


def test_schema_requires_exact_bindings_and_blocked_gates() -> None:
    schema = json.loads((ROOT / "schemas/candidate-image-manifest.v1.schema.json").read_text())
    assert schema["additionalProperties"] is False
    assert schema["properties"]["head_sha"]["pattern"] == "^[0-9a-f]{40}$"
    assert schema["properties"]["image_digest"]["pattern"] == "^sha256:[0-9a-f]{64}$"
    assert schema["properties"]["production_deployment_gate"]["const"] == "blocked"
    assert schema["properties"]["production_activation_gate"]["const"] == "blocked"


def test_cli_missing_input_emits_one_fail_closed_json(tmp_path: Path) -> None:
    output = tmp_path / "candidate-image-manifest.json"
    completed = subprocess.run(
        [sys.executable, str(PATH), "--output", str(output)],
        text=True, capture_output=True, check=False, env={},
    )
    assert completed.returncode != 0
    assert completed.stderr == ""
    lines = completed.stdout.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["candidate_manifest_gate"] == "FAIL"
    assert not output.exists()
