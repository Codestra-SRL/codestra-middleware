"""Constrained HTTP transport for the durable outbox.

This module has no URL discovery and never accepts a destination from an
untrusted payload. Targets are selected from configured service URLs only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from dataclasses import dataclass
from secrets import token_hex, token_urlsafe
from typing import Any

import httpx

from app.core.automation import redact
from app.core.config import settings


@dataclass(frozen=True)
class DispatchResult:
    outcome: str  # delivered, retry, permanent
    status_code: int | None = None
    error: str | None = None
    response: dict[str, Any] | None = None


class CircuitOpen(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, threshold: int = 5) -> None:
        self.threshold = threshold
        self.failures = 0
        self.open = False

    def success(self) -> None:
        self.failures = 0
        self.open = False

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.open = True

    def check(self) -> None:
        if self.open:
            raise CircuitOpen("outbox target circuit is open")


BREAKERS: dict[str, CircuitBreaker] = {}


def target_for(topic: str) -> tuple[str, str]:
    if topic in {"event.accepted", "n8n.event.ingest"}:
        if not settings.n8n_webhook_url:
            raise ValueError("n8n webhook URL is not configured")
        return "n8n", settings.n8n_webhook_url
    if topic in {"integration.result", "odoo.result"}:
        if not settings.odoo_results_url:
            raise ValueError("Odoo result URL is not configured")
        return "odoo", settings.odoo_results_url
    raise ValueError("outbox topic is not externally dispatchable")


def _body(payload: dict[str, Any]) -> bytes:
    return json.dumps(redact(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


N8N_EVENT_TYPES = frozenset({
    "call.completed", "callback.due", "lead.enrichment_requested",
    "lead.hot", "report.daily_requested",
})


def _n8n_payload(
    topic: str, payload: dict[str, Any], middleware_outbox_id: str
) -> dict[str, Any]:
    if topic != "event.accepted":
        return payload
    source = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    event_type = payload.get("event_type") or source.get("event_type")
    if event_type not in N8N_EVENT_TYPES:
        raise ValueError("event is not in the registered n8n event catalog")
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "event_id": str(payload.get("event_id") or source.get("event_id")),
        "event_type": event_type,
        "event_version": "1.0",
        "occurred_at": source.get("occurred_at") or now,
        "received_at": now,
        "tenant_id": str(source.get("tenant_id") or "codestra"),
        "environment": str(source.get("environment") or "staging"),
        "request_id": str(source.get("request_id") or payload.get("event_id")),
        "correlation_id": str(payload.get("correlation_id") or source.get("correlation_id")),
        "idempotency_key": str(source.get("idempotency_key") or payload.get("event_id")),
        "source": str(source.get("source") or "odoo"),
        "campaign_id": str(payload.get("campaign_id") or source.get("campaign_id") or "TEST_SYN"),
        "originating_odoo_outbox_id": str(
            source.get("originating_odoo_outbox_id") or payload.get("event_id")
        ),
        "originating_middleware_outbox_id": middleware_outbox_id,
        "synthetic": bool(source.get("synthetic", False)),
        "references": source.get("references") or {},
        "data": source.get("data") or source.get("payload") or {},
    }


def _headers(target: str, payload: dict[str, Any], body: bytes) -> dict[str, str]:
    identity_key = "result_id" if target == "odoo" else "event_id"
    event_id = str(payload.get(identity_key) or payload.get("event_id") or payload.get("idempotency_key") or token_urlsafe(16))
    timestamp = str(int(time.time()))
    nonce = token_urlsafe(18)
    secret = settings.outbox_signature_secret
    if not secret:
        raise ValueError("outbox signing secret is not configured")
    if target == "n8n":
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers = {
            "X-Codestra-Event-ID": event_id,
            "X-Codestra-Workflow-ID": str(payload.get("workflow_key") or "N8-CODESTRA-EVENT-ROUTER"),
            "X-Codestra-Timestamp": timestamp,
            "X-Codestra-Signature": f"sha256={digest}",
        }
    else:
        digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        headers = {
            "X-Codestra-Result-ID": event_id,
            "X-Codestra-Timestamp": timestamp,
            "X-Codestra-Signature": digest,
            "Idempotency-Key": str(payload["idempotency_key"]),
            "X-Codestra-Request-ID": str(payload["result_public_id"]),
            "X-Codestra-Correlation-ID": str(payload["correlation_id"]),
            "X-Codestra-Causation-ID": str(payload["event_id"]),
            "traceparent": f"00-{token_hex(16)}-{token_hex(8)}-01",
        }
    headers.update({
        "X-Codestra-Key-ID": settings.outbox_signature_key_id,
        "X-Codestra-Nonce": nonce,
        "X-Codestra-Body-SHA256": hashlib.sha256(body).hexdigest(),
        "Content-Type": "application/json",
    })
    return headers


async def dispatch(
    payload: dict[str, Any],
    topic: str,
    middleware_outbox_id: str,
    client: httpx.AsyncClient | None = None,
) -> DispatchResult:
    try:
        target, url = target_for(topic)
        breaker = BREAKERS.setdefault(target, CircuitBreaker(settings.outbox_circuit_failure_threshold))
        breaker.check()
        outbound_payload = (
            _n8n_payload(topic, payload, middleware_outbox_id)
            if target == "n8n" else payload
        )
        body = _body(outbound_payload)
        headers = _headers(target, outbound_payload, body)
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=httpx.Timeout(
                settings.outbox_http_request_timeout_seconds,
                connect=settings.outbox_http_connect_timeout_seconds,
            ), verify=settings.outbox_target_ca_file or True)
        if target == "odoo":
            if not all((settings.odoo_token_url, settings.odoo_client_id, settings.odoo_client_secret, settings.odoo_audience, settings.odoo_scope)):
                raise ValueError("Odoo service-token configuration is incomplete")
            token_client = httpx.AsyncClient(
                timeout=httpx.Timeout(5.0),
                verify=settings.outbox_target_ca_file or True,
            )
            try:
                token_response = await token_client.post(
                    settings.odoo_token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": settings.odoo_client_id,
                        "client_secret": settings.odoo_client_secret,
                        "audience": settings.odoo_audience,
                        "scope": settings.odoo_scope,
                    },
                )
                token_response.raise_for_status()
                token = token_response.json().get("access_token")
                if not token:
                    raise ValueError("Keycloak token response has no access token")
                headers["Authorization"] = f"Bearer {token}"
            finally:
                await token_client.aclose()
        try:
            response = await client.post(url, content=body, headers=headers)
        finally:
            if own_client:
                await client.aclose()
        if 200 <= response.status_code < 300:
            breaker.success()
            try:
                response_json = response.json()
            except ValueError:
                response_json = {"text": response.text[:1024]}
            return DispatchResult("delivered", response.status_code, response=response_json)
        if response.status_code == 429 or response.status_code >= 500:
            breaker.failure()
            return DispatchResult("retry", response.status_code, error=f"target returned {response.status_code}")
        breaker.failure()
        return DispatchResult("permanent", response.status_code, error=f"target rejected request with {response.status_code}")
    except CircuitOpen as exc:
        return DispatchResult("retry", error=str(exc))
    except (httpx.HTTPError, OSError, ValueError) as exc:
        return DispatchResult("retry", error=str(exc))
