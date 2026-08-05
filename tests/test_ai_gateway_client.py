import httpx
import json
import pytest

from app.adapters.ai_gateway.client import AIGatewayClient


@pytest.mark.asyncio
async def test_gateway_health_is_safe_and_does_not_return_credentials():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        assert "authorization" not in {key.lower() for key in request.headers}
        return httpx.Response(200, json={"ok": True})

    client = AIGatewayClient("http://qwen.test", transport=httpx.MockTransport(handler))
    try:
        result = await client.health()
    finally:
        await client.aclose()
    assert result["status"] == "HEALTHY"
    assert "endpoint" not in result


@pytest.mark.asyncio
async def test_gateway_chat_completion_uses_openai_compatible_path():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["schema_code"] == "lead_normalization_v1"
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = AIGatewayClient("http://qwen.test", transport=httpx.MockTransport(handler))
    try:
        result = await client.chat_completion({"schema_code": "lead_normalization_v1"})
    finally:
        await client.aclose()
    assert result["choices"]
