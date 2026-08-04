import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.internal import ai
from app.core.config import settings

app = FastAPI()
app.include_router(ai.router)

async def authenticated_service() -> str:
    return "qwen-ai-01"


def setup_module():
    app.dependency_overrides[ai.authenticate] = authenticated_service
    settings.ai_private_api_enabled = True
    settings.ai_audit_log_file = ""
    ai._commands.clear()
    ai._idempotency.clear()
    ai._callback_idempotency.clear()


def test_contract_auth_replay_idempotency_and_mock_e2e():
    client = TestClient(app)
    health_path = "/internal/api/v1/ai/health"
    assert client.get(health_path).json()["mode"] == "mock-only"

    path = "/internal/api/v1/ai/commands"
    payload = {"action": "odoo.lookup", "target": "odoo", "arguments": {"record": 7}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    context = {"X-Correlation-ID": "corr-test-1", "Idempotency-Key": "fixture-key-1001",
               "Content-Type": "application/json"}
    response = client.post(path, content=body, headers=context)
    assert response.status_code == 202
    result = response.json()
    assert result["result"]["downstream_contacted"] is False
    assert result["result"]["writes_performed"] is False

    duplicate = client.post(path, content=body, headers=context)
    assert duplicate.status_code == 202
    assert duplicate.json()["command_id"] == result["command_id"]
    assert duplicate.json()["idempotent_replay"] is True

    wrong = {"action": "n8n.inspect", "target": "odoo", "arguments": {}}
    wrong_body = json.dumps(wrong, separators=(",", ":")).encode()
    assert client.post(path, content=wrong_body, headers=context).status_code == 403

    get_path = f"/internal/api/v1/ai/commands/{result['command_id']}"
    assert client.get(get_path).status_code == 200

    callback_path = "/internal/api/v1/ai/callbacks/qwen"
    callback = {"command_id": result["command_id"], "event": "completed", "data": {"ok": True}}
    callback_body = json.dumps(callback, separators=(",", ":")).encode()
    callback_response = client.post(callback_path, content=callback_body, headers=context)
    assert callback_response.status_code == 202
    assert callback_response.json()["dispatch_performed"] is False
