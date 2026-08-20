from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "webrtc-production-preflight"
loader = importlib.machinery.SourceFileLoader("webrtc_preflight", str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)


def release() -> dict:
    return {"protected_source_sha": "a" * 40, "image_digest": "sha256:" + "b" * 64}


def technical(gate: str) -> dict:
    return {"gates": {gate: "PASS"}}


def test_local_only_signature_sbom_and_provenance_are_rejected() -> None:
    for gate, record_name in module.PROTECTED_RELEASE_GATES.items():
        data = technical(gate)
        data["protected_release"] = {
            record_name: {
                "status": "PASS",
                "authority": "local",
                "verification": "PASS",
                "source_sha": release()["protected_source_sha"],
                "image_digest": release()["image_digest"],
                "workflow_run_id": "local",
                "artifact_id": "local",
            }
        }
        assert not module.authoritative_gate(gate, data, release())


def test_partial_backup_references_are_rejected() -> None:
    data = technical("BACKUP_REFERENCES")
    data["backups"] = {"middleware": {"verification": "PASS"}}
    assert not module.authoritative_gate("BACKUP_REFERENCES", data, release())


def test_unapproved_running_digest_is_rejected() -> None:
    data = technical("CURRENT_ARTIFACT_BINDING")
    data["current_artifact_binding"] = {
        "running_digest": "sha256:running",
        "approved_digest": "sha256:other",
        "approval_reference": "approval/1",
    }
    assert not module.authoritative_gate("CURRENT_ARTIFACT_BINDING", data, release())


def test_missing_rollback_artifact_is_rejected() -> None:
    data = technical("ROLLBACK_ARTIFACT")
    assert not module.authoritative_gate("ROLLBACK_ARTIFACT", data, release())


def test_missing_human_records_are_not_approvals() -> None:
    approvals = {"security_owner": {"decision": None}}
    missing = [name for name, item in approvals.items() if item.get("decision") != "APPROVE"]
    assert missing == ["security_owner"]


def test_disabled_dialing_is_a_passing_safety_control(monkeypatch) -> None:
    monkeypatch.delenv("LIVE_PSTN_DIALING", raising=False)
    monkeypatch.delenv("PRODUCTION_DIALING_ENABLED", raising=False)
    assert module.os.getenv("LIVE_PSTN_DIALING", "false").lower() == "false"
    assert module.os.getenv("PRODUCTION_DIALING_ENABLED", "false").lower() == "false"
