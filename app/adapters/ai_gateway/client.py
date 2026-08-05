"""OpenAI-compatible private AI Gateway client.

The client is intentionally provider-agnostic: Qwen serving details stay behind
the gateway and credentials are loaded from a root-owned secret file.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from app.metrics import (
    AI_GATEWAY_FAILURES,
    AI_GATEWAY_REQUESTS,
    AI_GATEWAY_TIMEOUTS,
    AI_GATEWAY_DURATION,
)


def _read_secret(path: str) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8").strip()


class AIGatewayClient:
    def __init__(
        self,
        base_url: str,
        api_key_file: str = "",
        *,
        timeout_seconds: float = 120,
        model_code: str = "qwen-primary",
        health_path: str = "/health",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_file = api_key_file
        self.timeout_seconds = timeout_seconds
        self.model_code = model_code
        self.health_path = "/" + health_path.lstrip("/")
        self.http = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
        )

    async def aclose(self) -> None:
        await self.http.aclose()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = _read_secret(self.api_key_file)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return headers

    async def health(self) -> dict[str, Any]:
        if not self.base_url:
            return {"status": "DISABLED", "reason": "endpoint_not_configured"}
        started = time.perf_counter()
        try:
            response = await self.http.get(
                f"{self.base_url}{self.health_path}",
                headers=self._headers(),
                timeout=httpx.Timeout(10, connect=5),
            )
            response.raise_for_status()
        except (httpx.HTTPError, OSError) as exc:
            AI_GATEWAY_FAILURES.inc()
            return {"status": "UNAVAILABLE", "error_class": type(exc).__name__}
        return {
            "status": "HEALTHY",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    async def chat_completion(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("AI Gateway is not configured")
        started = time.perf_counter()
        AI_GATEWAY_REQUESTS.labels(self.model_code).inc()
        try:
            response = await self.http.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json=request,
                timeout=httpx.Timeout(self.timeout_seconds, connect=10),
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            AI_GATEWAY_TIMEOUTS.inc()
            AI_GATEWAY_FAILURES.inc()
            raise
        except (httpx.HTTPError, ValueError):
            AI_GATEWAY_FAILURES.inc()
            raise
        finally:
            AI_GATEWAY_DURATION.labels(self.model_code).observe(
                time.perf_counter() - started
            )
