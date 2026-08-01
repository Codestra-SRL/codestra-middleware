from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("validator", ROOT / "scripts/security/validate-security-owner-decision.py")
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
ZERO = "0" * 64


def request(tmp_path: Path) -> tuple[dict, Path]:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    document = {
        "schema_version": 1, "request_type": "security_owner_decision_request",
        "repository": "Codestra-SRL/codestra-middleware", "pr_number": 68,
        "pr_head_sha": "1" * 40, "middleware_main_sha": "2" * 40, "odoo_main_sha": "3" * 40,
        "created_at_utc": now.isoformat().replace("+00:00", "Z"),
        "requested_expiration_utc": (now + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "approved_scope": "server_a_isolated_staging",
        "image_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "image_digests": {"middleware": "sha256:" + ZERO}, "vulnerability_findings": [],
        "compensating_controls": {"path": "evidence/controls.json", "sha256": ZERO},
        "odoo_isolation_evidence": {"path": "evidence/odoo.json", "sha256": ZERO},
        "middleware_isolation_evidence": {"path": "evidence/middleware.json", "sha256": ZERO},
        "limitations": [],
        "negative_authorizations": {name: "blocked" for name in VALIDATOR.BLOCKED},
        "revocation_conditions": ["head changes"],
    }
    return document, manifest


def test_valid_request(tmp_path: Path) -> None:
    document, manifest = request(tmp_path)
    VALIDATOR.validate_request(document, str(manifest), "68", "1" * 40)


@pytest.mark.parametrize("field", ["staging_deployment_gate", "production_deployment_gate", "server_b_access_gate", "customer_data_gate"])
def test_allowed_gate_rejected(tmp_path: Path, field: str) -> None:
    document, manifest = request(tmp_path)
    document["negative_authorizations"][field] = "allowed"
    with pytest.raises(SystemExit):
        VALIDATOR.validate_request(document, str(manifest), "68", "1" * 40)


def test_wrong_head_hash_and_expiration_rejected(tmp_path: Path) -> None:
    document, manifest = request(tmp_path)
    for mutation in ("head", "hash", "expiry"):
        changed = json.loads(json.dumps(document))
        if mutation == "head": changed["pr_head_sha"] = "4" * 40
        if mutation == "hash": changed["image_manifest_sha256"] = ZERO
        if mutation == "expiry": changed["requested_expiration_utc"] = (datetime.now(timezone.utc) + timedelta(days=31)).isoformat()
        with pytest.raises(SystemExit):
            VALIDATOR.validate_request(changed, str(manifest), "68", "1" * 40)


def test_workflow_is_inert_and_pinned() -> None:
    workflow = (ROOT / ".github/workflows/security-owner-decision-sign.yml").read_text(encoding="utf-8")
    assert "security_findings_json" not in workflow
    assert "compensating_controls_json" not in workflow
    assert "environment: security-owner-signing" in workflow
    assert "id-token: write" in workflow
    assert "pull_request_target" not in workflow
    assert "ref: ${{ github.sha }}" in workflow
    assert "scripts/security/validate-security-owner-decision.py" in workflow
    for line in workflow.splitlines():
        if "uses:" in line:
            ref = line.rsplit("@", 1)[-1]
            assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref)
