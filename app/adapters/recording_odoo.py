"""Idempotent Odoo metadata writer using the existing signed integration API."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx


class OdooRecordingWriter:
    def __init__(
        self,
        endpoint: str,
        secret: bytes,
        client: httpx.Client | None = None,
    ) -> None:
        if not endpoint.startswith("https://"):
            raise ValueError("Odoo recording endpoint must use HTTPS")
        self.endpoint = endpoint
        self.secret = secret
        self.client = client or httpx.Client(timeout=10)

    def upsert(self, payload: dict[str, object]) -> str:
        body = json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(
            self.secret,
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        response = self.client.post(
            self.endpoint,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Codestra-Timestamp": timestamp,
                "X-Codestra-Signature": signature,
                "X-Codestra-Event-ID": str(payload["recording_uid"]),
            },
        )
        response.raise_for_status()
        result = response.json()
        if (
            result.get("recording_uid") != payload["recording_uid"]
            or result.get("state") != "ODOO_LINKED"
        ):
            raise ValueError("invalid Odoo recording acknowledgement")
        return str(result["recording_uid"])
