#!/usr/bin/env python3
"""Outbound-only Qwen worker; it never opens a listening socket."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import http.client
import json
import secrets
import signal
import socket
import ssl
import time
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIDDLEWARE_IP = "10.40.0.1"
MIDDLEWARE_NAME = "middleware.internal.codestra.agency"
SERVICE_ID = "qwen-ai-01"
KEY_ID = "qwen-ai-01-hmac-20260804-01"
BASE = Path("/run/codestra-qwen-worker")
WORKER_ID = "qwen-ai-01-worker"
ALLOWED_TYPES = frozenset({
    "ai.chat.v1", "ai.coding.v1", "ai.crm.v1", "ai.voice.v1", "ai.embeddings.v1"
})
MODEL_REGISTRY = {
    "fast-chat": ("litellm", "qwen-runtime-fast"),
    "quality-chat": ("litellm", "qwen-coder-review"),
    "coding-default": ("litellm", "qwen-coder-fallback"),
    "coding-large": ("litellm", "qwen-coder-primary"),
    "crm-analysis": ("litellm", "qwen-runtime-fast"),
    "voice-summary": ("litellm", "qwen-voice-fast"),
    "embedding-default": None,
}


class WorkerError(RuntimeError):
    pass


def protected(path: Path) -> Path:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise WorkerError("required credential file is unavailable")
    if path.stat().st_mode & 0o077:
        raise WorkerError("credential permissions are unsafe")
    return path


def encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def signed_headers(method: str, path: str, body: bytes, secret_file: Path) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = secrets.token_urlsafe(24)
    digest = hashlib.sha256(body).hexdigest()
    canonical = f"{method.upper()}\n{path}\n{SERVICE_ID}\n{timestamp}\n{nonce}\n{digest}".encode("ascii")
    secret = protected(secret_file).read_bytes().strip()
    if len(secret) != 64:
        raise WorkerError("HMAC enrollment is invalid")
    return {
        "Content-Type": "application/json", "X-Service-ID": SERVICE_ID,
        "X-HMAC-Key-ID": KEY_ID, "X-Timestamp": timestamp, "X-Nonce": nonce,
        "X-Body-SHA256": digest,
        "X-Signature": hmac.new(secret, canonical, hashlib.sha256).hexdigest(),
        "X-Correlation-ID": f"qwen-worker-{uuid.uuid4()}",
    }


class PinnedConnection(http.client.HTTPSConnection):
    def __init__(self, context: ssl.SSLContext) -> None:
        super().__init__(MIDDLEWARE_NAME, 443, context=context, timeout=10)
        self._context = context

    def connect(self) -> None:
        raw = socket.create_connection((MIDDLEWARE_IP, 443), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=MIDDLEWARE_NAME)


@dataclass(slots=True)
class Middleware:
    context: ssl.SSLContext
    secret_file: Path

    @classmethod
    def create(cls) -> Middleware:
        context = ssl.create_default_context(cafile=str(protected(BASE / "private-ca.crt")))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(protected(BASE / "client.crt")), str(protected(BASE / "client.key")))
        return cls(context, protected(BASE / "hmac.key"))

    def request(self, method: str, path: str, value: object) -> tuple[int, dict[str, Any]]:
        body = encode(value)
        connection = PinnedConnection(self.context)
        try:
            connection.request(method, path, body, signed_headers(method, path, body, self.secret_file))
            response = connection.getresponse()
            payload = response.read(1_048_577)
            if len(payload) > 1_048_576:
                raise WorkerError("middleware response exceeds bound")
            document = json.loads(payload) if payload else {}
            if not isinstance(document, dict):
                raise WorkerError("middleware response schema is invalid")
            return response.status, document
        except (OSError, ssl.SSLError, http.client.HTTPException, json.JSONDecodeError) as exc:
            raise WorkerError("bounded middleware request failed") from exc
        finally:
            connection.close()


def loopback_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    if not (url.startswith("http://127.0.0.1:") or url.startswith("http://[::1]:")):
        raise WorkerError("non-loopback model endpoint rejected")
    request = urllib.request.Request(url, data=encode(payload), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            raw = response.read(1_048_577)
    except OSError as exc:
        raise WorkerError("loopback model unavailable") from exc
    if len(raw) > 1_048_576:
        raise WorkerError("model result exceeds bound")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise WorkerError("model result schema is invalid")
    return result


def execute(job: dict[str, Any]) -> dict[str, Any]:
    command_type = job.get("command_type")
    payload = job.get("command_payload")
    profile = job.get("model_profile")
    if command_type not in ALLOWED_TYPES or not isinstance(payload, dict) or profile not in MODEL_REGISTRY:
        raise WorkerError("unsupported job contract")
    capability = MODEL_REGISTRY[profile]
    if capability is None:
        raise WorkerError("capability unavailable")
    provider, model = capability
    limits = job.get("resource_limits") or {}
    timeout = min(int(limits.get("runtime_seconds", 300)), 600)
    started = time.time()
    if provider == "ollama-embeddings":
        source = payload.get("input", {}).get("texts") or [payload.get("input", {}).get("text", "")]
        raw = loopback_json("http://127.0.0.1:11434/api/embed", {"model": model, "input": source}, timeout)
        output = {"embeddings": raw.get("embeddings", []), "dimension": len((raw.get("embeddings") or [[]])[0])}
    elif provider == "ollama":
        prompt = json.dumps(payload.get("input", {}), sort_keys=True)
        raw = loopback_json("http://127.0.0.1:11434/api/generate",
                            {"model": model, "prompt": prompt, "stream": False}, timeout)
        output = {"proposal": raw.get("response", "")}
    else:
        prompt = json.dumps(payload.get("input", {}), sort_keys=True)
        raw = loopback_json("http://127.0.0.1:4000/v1/chat/completions", {
            "model": model, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": payload.get("model_policy", {}).get("max_tokens", 1024),
        }, timeout)
        choices = raw.get("choices") or []
        output = {"proposal": choices[0].get("message", {}).get("content", "") if choices else ""}
    completed = time.time()
    return {
        "command_id": job["id"], "job_id": job["id"], "status": "SUCCEEDED",
        "result_schema_version": "1.0", "model_used": model, "provider_used": provider.split("-")[0],
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(completed)),
        "latency_ms": int((completed - started) * 1000), "token_usage": {},
        "resource_usage": {}, "output": output, "structured_artifacts": [],
        "warnings": [], "policy_decisions": ["outbound-only", "proposal-only"],
        "error": None, "retryability": "none", "audit_reference": f"audit-{job['id']}",
    }


def run_once(api: Middleware) -> str:
    status, response = api.request("POST", "/internal/api/v1/ai/worker/jobs/claim", {"worker_id": WORKER_ID})
    if status == 503:
        return "claims-disabled"
    if status != 200:
        raise WorkerError("claim rejected")
    job = response.get("job")
    if job is None:
        return "empty"
    if not isinstance(job, dict):
        raise WorkerError("claim schema invalid")
    job_id, token = str(job["id"]), int(job["fencing_token"])
    mutation = {"worker_id": WORKER_ID, "fencing_token": token}
    try:
        result = execute(job)
        status, _ = api.request("POST", f"/internal/api/v1/ai/worker/jobs/{job_id}/complete",
                                {**mutation, "result": result})
        if status not in (200, 409):
            raise WorkerError("completion rejected")
        return "completed" if status == 200 else "duplicate-completion"
    except WorkerError:
        api.request("POST", f"/internal/api/v1/ai/worker/jobs/{job_id}/fail",
                    {**mutation, "error_code": "model_unavailable", "retryable": True})
        return "failed-retryable"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        Middleware.create()
        print("WORKER_CONFIGURATION=PASS")
        return 0
    api = Middleware.create()
    if args.once:
        print(f"WORKER_OUTCOME={run_once(api)}")
        return 0
    stopping = False

    def stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    delay = 2.0
    while not stopping:
        try:
            outcome = run_once(api)
            delay = 2.0
            if outcome in {"empty", "claims-disabled"}:
                time.sleep(2)
        except WorkerError:
            time.sleep(delay)
            delay = min(delay * 2, 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
