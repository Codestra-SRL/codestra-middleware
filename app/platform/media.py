from __future__ import annotations

from pathlib import Path
from typing import Protocol
from uuid import UUID


class StorageBackend(Protocol):
    async def put(self, asset_id: UUID, content: bytes) -> str: ...
    async def delete(self, reference: str) -> None: ...


class LocalStorageBackend:
    """Staging backend; references are opaque and paths never leave this boundary."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    async def put(self, asset_id: UUID, content: bytes) -> str:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = (self.root / str(asset_id)).resolve()
        if target.parent != self.root:
            raise ValueError("SOCIAL_MEDIA_LOCATION_INVALID")
        target.write_bytes(content)
        target.chmod(0o600)
        return f"media://local/{asset_id}"

    async def delete(self, reference: str) -> None:
        asset_id = UUID(reference.removeprefix("media://local/"))
        target = (self.root / str(asset_id)).resolve()
        if target.parent != self.root:
            raise ValueError("SOCIAL_MEDIA_LOCATION_INVALID")
        target.unlink(missing_ok=True)


class ObjectStorageBackend:
    async def put(self, asset_id: UUID, content: bytes) -> str:
        raise RuntimeError("OBJECT_STORAGE_NOT_CONFIGURED")

    async def delete(self, reference: str) -> None:
        raise RuntimeError("OBJECT_STORAGE_NOT_CONFIGURED")
