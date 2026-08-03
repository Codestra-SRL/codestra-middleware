import hashlib
import hmac
import json
import time
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.internal import ai
from app.core.config import settings

app = FastAPI()
app.include_router(ai.router)


SECRET = b"test-only-secret-material-at-least-32-bytes"


def signed(method: str, path: str, body: bytes = b"", nonce: str | None = None, **extra):
    timestamp = str(int(time.time()))
    nonce = nonce or uuid4().hex
    canonical = "\n".join((method, path, "qwen", timestamp, nonce, hashlib.sha256(body).hexdigest()))
    signature = hmac.new(SECRET, canonical.encode(), hashlib.sha256).hexdigest()
    return {"X-Service-ID": "qwen", "X-Timestamp": timestamp, "X-Nonce": nonce,
            "X-Signature": signature, **extra}


def setup_module():
    path = Path("/tmp/codestra-qwen-test-hmac")
    path.write_bytes(SECRET)
    settings.ai_hmac_secret_file = str(path)
    settings.ai_private_api_enabled = True
    settings.ai_audit_log_file = "/tmp/codestra-qwen-test-audit.jsonl"
    ai._commands.clear()
    ai._idempotency.clear()
    ai._callback_idempotency.clear()
    ai._nonces.clear()
    ai._rate.clear()


def test_contract_auth_replay_idempotency_and_mock_e2e():
    client = TestClient(app)
    health_path = "/internal/api/v1/ai/health"
    assert client.get(health_path, headers=signed("GET", health_path)).json()["mode"] == "mock-only"
    assert client.get(health_path).status_code == 422

    path = "/internal/api/v1/ai/commands"
    payload = {"action": "odoo.lookup", "target": "odoo", "arguments": {"record": 7}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    context = {"X-Correlation-ID": "corr-test-1", "Idempotency-Key": "fixture-key-1001",
               "Content-Type": "application/json"}
    response = client.post(path, content=body, headers=signed("POST", path, body, **context))
    assert response.status_code == 202
    result = response.json()
    assert result["result"]["downstream_contacted"] is False
    assert result["result"]["writes_performed"] is False

    duplicate = client.post(path, content=body, headers=signed("POST", path, body, **context))
    assert duplicate.status_code == 202
    assert duplicate.json()["command_id"] == result["command_id"]
    assert duplicate.json()["idempotent_replay"] is True

    nonce = uuid4().hex
    replay_headers = signed("GET", health_path, nonce=nonce)
    assert client.get(health_path, headers=replay_headers).status_code == 200
    assert client.get(health_path, headers=replay_headers).status_code == 409

    wrong = {"action": "n8n.inspect", "target": "odoo", "arguments": {}}
    wrong_body = json.dumps(wrong, separators=(",", ":")).encode()
    assert client.post(path, content=wrong_body, headers=signed("POST", path, wrong_body, **context)).status_code == 403

    get_path = f"/internal/api/v1/ai/commands/{result['command_id']}"
    assert client.get(get_path, headers=signed("GET", get_path)).status_code == 200

    callback_path = "/internal/api/v1/ai/callbacks/qwen"
    callback = {"command_id": result["command_id"], "event": "completed", "data": {"ok": True}}
    callback_body = json.dumps(callback, separators=(",", ":")).encode()
    callback_response = client.post(callback_path, content=callback_body,
        headers=signed("POST", callback_path, callback_body, **context))
    assert callback_response.status_code == 202
    assert callback_response.json()["dispatch_performed"] is False
