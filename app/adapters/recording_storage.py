"""MinIO adapter using least-privilege Middleware credentials."""

from __future__ import annotations

from datetime import datetime, timedelta

from minio import Minio

from app.core.recordings import ObjectHead


class MinioRecordingStore:
    def __init__(self, client: Minio, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    @staticmethod
    def _object_name(opaque_id: str) -> str:
        if not opaque_id or not opaque_id.replace("-", "").replace("_", "").isalnum():
            raise ValueError("invalid opaque object identifier")
        return f"staging/{opaque_id}"

    def reserve(self, opaque_id: str, expires_in: int) -> tuple[str, datetime]:
        expires = timedelta(seconds=min(expires_in, 300))
        url = self.client.presigned_put_object(
            self.bucket, self._object_name(opaque_id), expires=expires
        )
        return url, datetime.now().astimezone() + expires

    def head(self, opaque_id: str) -> ObjectHead:
        stat = self.client.stat_object(
            self.bucket, self._object_name(opaque_id)
        )
        metadata = {
            key.lower(): value for key, value in (stat.metadata or {}).items()
        }
        checksum = metadata.get("x-amz-meta-sha256", "")
        if (
            stat.size is None
            or stat.content_type is None
            or stat.version_id is None
        ):
            raise ValueError("incomplete object identity")
        return ObjectHead(
            size_bytes=stat.size,
            checksum_sha256=checksum,
            content_type=stat.content_type,
            version_id=stat.version_id,
        )

    def playback(self, opaque_id: str, expires_in: int) -> tuple[str, datetime]:
        expires = timedelta(seconds=min(expires_in, 120))
        url = self.client.presigned_get_object(
            self.bucket, self._object_name(opaque_id), expires=expires
        )
        return url, datetime.now().astimezone() + expires
