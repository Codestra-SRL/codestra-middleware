from __future__ import annotations

from typing import Any, Protocol

import httpx


class OdooRecordingPort(Protocol):
    async def upsert(
        self, metadata: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]: ...


class OdooRecordingClient:
    """Service-authenticated metadata-only client for authoritative Odoo writes."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        environment: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.startswith("https://") or not service_token:
            raise ValueError("Odoo HTTPS service authentication is required")
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token
        self.environment = environment
        self.client = client or httpx.AsyncClient(timeout=15)

    async def upsert(
        self, metadata: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        forbidden = {"file", "audio", "mp3", "upload_url", "object_key"}
        if forbidden.intersection(metadata):
            raise ValueError("Odoo recording request must contain metadata only")
        response = await self.client.post(
            f"{self.base_url}/codestra/api/v1/recordings/upsert",
            json=metadata,
            headers={
                "Authorization": f"Bearer {self.service_token}",
                "X-Environment": self.environment,
                "Idempotency-Key": idempotency_key,
            },
        )
        response.raise_for_status()
        body = response.json()
        if body.get("acknowledged") is not True:
            raise RuntimeError("Odoo did not acknowledge recording upsert")
        return body

    async def get(self, recording_uid: str) -> dict[str, Any]:
        response = await self.client.get(
            f"{self.base_url}/codestra/api/v1/recordings/{recording_uid}",
            headers={
                "Authorization": f"Bearer {self.service_token}",
                "X-Environment": self.environment,
            },
        )
        response.raise_for_status()
        return response.json()

    async def update_status(
        self,
        recording_uid: str,
        status: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        response = await self.client.post(
            f"{self.base_url}/codestra/api/v1/recordings/{recording_uid}/status",
            json=status,
            headers={
                "Authorization": f"Bearer {self.service_token}",
                "X-Environment": self.environment,
                "Idempotency-Key": idempotency_key,
            },
        )
        response.raise_for_status()
        return response.json()


class AcknowledgingOdooClient:
    async def upsert(
        self, metadata: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        return {"acknowledged": True, "recording_uid": metadata["recording_uid"]}
