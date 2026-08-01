import asyncio

import httpx

from app.core.config import settings
from app.workers.outbox_dispatcher import BREAKERS, dispatch


def run(coro):
    return asyncio.run(coro)


async def dispatch_with_transport(payload, topic, handler):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await dispatch(payload, topic, "middleware-outbox-test", client)


def configure(monkeypatch):
    monkeypatch.setattr(settings, "n8n_webhook_url", "https://n8n.test/webhook/v1/events")
    monkeypatch.setattr(settings, "odoo_results_url", "https://odoo.test/api/v1/integration/results")
    monkeypatch.setattr(settings, "outbox_signature_secret", "test-secret")
    monkeypatch.setattr(settings, "outbox_signature_key_id", "staging-key")
    BREAKERS.clear()


def test_n8n_delivery_signs_exact_body_and_accepts_202(monkeypatch):
    configure(monkeypatch)
    captured = {}

    def handler(request: httpx.Request):
        captured["body"] = request.content
        captured["headers"] = request.headers
        return httpx.Response(202, json={"accepted": True})

    result = run(dispatch_with_transport({"event_id": "evt-1", "event_type": "lead.hot", "safe": True}, "event.accepted", handler))
    assert result.outcome == "delivered"
    assert captured["headers"]["x-codestra-workflow-id"].startswith("N8-")
    assert captured["headers"]["x-codestra-body-sha256"]


def test_5xx_retries_and_4xx_dead_letters(monkeypatch):
    configure(monkeypatch)
    retry = run(dispatch_with_transport({"event_id": "evt-2", "event_type": "lead.hot"}, "event.accepted", lambda _: httpx.Response(503)))
    permanent = run(dispatch_with_transport({"event_id": "evt-3", "event_type": "lead.hot"}, "event.accepted", lambda _: httpx.Response(422)))
    assert retry.outcome == "retry"
    assert permanent.outcome == "permanent"
