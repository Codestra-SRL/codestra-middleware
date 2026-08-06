from __future__ import annotations

import hashlib
import hmac
import importlib.util
import sys
from contextlib import AbstractContextManager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "worker/qwen_polling_worker.py"
SPEC = importlib.util.spec_from_file_location("qwen_polling_worker_test", PATH)
assert SPEC and SPEC.loader
worker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = worker
SPEC.loader.exec_module(worker)


def test_signer_uses_authoritative_canonical_contract(tmp_path, monkeypatch):
    secret = tmp_path / "hmac"
    secret.write_bytes(b"a" * 64)
    secret.chmod(0o600)
    monkeypatch.setattr(worker.time, "time", lambda: 1_786_000_000)
    monkeypatch.setattr(worker.secrets, "token_urlsafe", lambda _: "fixture-nonce-1234567890")
    body = b'{"fixture":true}'
    headers = worker.signed_headers("post", "/internal/api/v1/ai/worker/jobs/claim", body, secret)
    digest = hashlib.sha256(body).hexdigest()
    canonical = (
        "POST\n/internal/api/v1/ai/worker/jobs/claim\nqwen-ai-01\n"
        f"1786000000\nfixture-nonce-1234567890\n{digest}"
    ).encode("ascii")
    assert headers["X-Signature"] == hmac.new(b"a" * 64, canonical, hashlib.sha256).hexdigest()
    assert headers["X-HMAC-Key-ID"] == "qwen-ai-01-hmac-20260804-01"


def test_non_loopback_model_destination_fails_closed():
    with pytest.raises(worker.WorkerError, match="non-loopback"):
        worker.loopback_json("http://10.40.0.4:11434/api/generate", {}, 1)


class FakeResponse(AbstractContextManager):
    def read(self, _limit):
        return b'{"choices":[]}'

    def __exit__(self, *_args):
        return None


def test_litellm_request_uses_dedicated_projected_bearer(tmp_path, monkeypatch):
    credential = tmp_path / "litellm.key"
    credential.write_text("fixture-value")
    credential.chmod(0o600)
    captured = {}

    def fake_open(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(worker.urllib.request, "urlopen", fake_open)
    assert worker.loopback_json(
        "http://127.0.0.1:4000/v1/chat/completions", {}, 7, credential
    ) == {"choices": []}
    assert captured == {"authorization": "Bearer fixture-value", "timeout": 7}


def test_protected_build_selects_middleware_runtime_stage():
    workflow = (ROOT / ".github/workflows/staging-candidate-build-sign.yml").read_text()
    build = workflow.split("- name: Build and publish staging-only candidate", 1)[1]
    build = build.split("- name: Resolve immutable candidate identity", 1)[0]
    assert "docker build" in build
    assert "--target runtime" in build


class FakeAPI:
    def __init__(self, job=None, completion_status=200):
        self.job = job
        self.completion_status = completion_status
        self.calls = []

    def request(self, method, path, value):
        self.calls.append((method, path, value))
        if path.endswith("/claim"):
            return 200, {"job": self.job}
        if path.endswith("/complete"):
            return self.completion_status, {"state": "completed"}
        return 200, {"state": "retry_wait"}


def fixture_job(command_type="ai.chat.v1", profile="fast-chat"):
    return {
        "id": "00000000-0000-4000-8000-000000000001", "command_type": command_type,
        "command_payload": {"input": {"text": "synthetic"}, "model_policy": {"max_tokens": 10}},
        "model_profile": profile, "resource_limits": {"runtime_seconds": 10},
        "fencing_token": 1,
    }


def test_worker_empty_completion_duplicate_and_failure_paths(monkeypatch):
    empty = FakeAPI()
    assert worker.run_once(empty) == "empty"
    successful = FakeAPI(fixture_job())
    monkeypatch.setattr(worker, "execute", lambda job: {
        "command_id": job["id"], "job_id": job["id"], "status": "SUCCEEDED",
        "result_schema_version": "1.0", "model_used": "fixture", "provider_used": "mock",
        "started_at": "2026-08-06T00:00:00Z", "completed_at": "2026-08-06T00:00:01Z",
        "latency_ms": 1, "token_usage": {}, "resource_usage": {}, "output": {"fixture": True},
        "structured_artifacts": [], "warnings": [], "policy_decisions": [], "error": None,
        "retryability": "none", "audit_reference": "audit-fixture",
    })
    assert worker.run_once(successful) == "completed"
    duplicate = FakeAPI(fixture_job(), completion_status=409)
    assert worker.run_once(duplicate) == "duplicate-completion"
    failed = FakeAPI(fixture_job("ai.embeddings.v1", "embedding-default"))
    monkeypatch.setattr(worker, "execute", lambda _job: (_ for _ in ()).throw(worker.WorkerError("model")))
    assert worker.run_once(failed) == "failed-retryable"
    assert failed.calls[-1][1].endswith("/fail")


def test_all_worker_command_families_are_allowlisted():
    assert worker.ALLOWED_TYPES == {
        "ai.chat.v1", "ai.coding.v1", "ai.crm.v1", "ai.voice.v1", "ai.embeddings.v1"
    }
    assert worker.MODEL_REGISTRY["embedding-default"] is None
