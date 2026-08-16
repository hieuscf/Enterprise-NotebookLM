# =============================================================================
# File: minio_storage.py
# Module/Service: Document Ingestion Service
# Layer: Adapter
# Purpose: MinIO/S3-compatible object storage client for document binaries (FR2).
# Responsibilities:
#   - Upload / download / delete versioned document bytes
#   - Ensure target bucket exists (dev convenience)
# Dependencies:
#   - minio SDK, app.core.config.Settings
# Public Exports:
#   - MinioStorageAdapter, ObjectNotFoundError, get_minio_storage
# Database/Table: N/A (paths stored on document_versions.storage_path)
# Related Modules: app.services.documents, app.workers.pipeline
# Important Notes: documents table never stores file bytes — only storage_path on versions.
# =============================================================================

from __future__ import annotations

import io
from functools import lru_cache
from typing import Any

from collections.abc import Iterator

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings, get_settings

_MISSING_OBJECT_CODES = frozenset({"NoSuchKey", "NoSuchObject", "NoSuchBucket"})


class ObjectNotFoundError(FileNotFoundError):
    """Object key is missing from the configured bucket."""


class MinioStorageAdapter:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.minio_bucket
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    def upload_bytes(
        self,
        *,
        object_key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        return self.upload_stream(
            object_key=object_key,
            stream=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )

    def upload_stream(
        self,
        *,
        object_key: str,
        stream: Any,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload from a file-like stream (supports large files without full RAM copy)."""
        self.ensure_bucket()
        self._client.put_object(
            self._bucket,
            object_key,
            stream,
            length=length,
            content_type=content_type,
        )
        return object_key

    def download_bytes(self, object_key: str) -> bytes:
        response = self._open_object(object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def iter_object(self, object_key: str, chunk_size: int = 65536) -> Iterator[bytes]:
        """Yield object bytes in chunks. Closes the MinIO connection when exhausted."""
        response = self._open_object(object_key)
        try:
            yield from response.stream(chunk_size)
        finally:
            response.close()
            response.release_conn()

    def object_size(self, object_key: str) -> int | None:
        try:
            stat = self._client.stat_object(self._bucket, object_key)
        except S3Error as exc:
            if exc.code in _MISSING_OBJECT_CODES:
                return None
            raise
        size = getattr(stat, "size", None)
        return int(size) if size is not None else None

    def _open_object(self, object_key: str) -> Any:
        try:
            return self._client.get_object(self._bucket, object_key)
        except S3Error as exc:
            if exc.code in _MISSING_OBJECT_CODES:
                raise ObjectNotFoundError(object_key) from exc
            raise

    def object_exists(self, object_key: str) -> bool:
        """Return True if ``object_key`` exists in the bucket."""
        try:
            self._client.stat_object(self._bucket, object_key)
            return True
        except S3Error:
            return False

    def delete_object(self, object_key: str) -> None:
        try:
            self._client.remove_object(self._bucket, object_key)
        except S3Error:
            # Best-effort cleanup — missing object is not fatal for delete flows.
            return


@lru_cache
def get_minio_storage() -> MinioStorageAdapter:
    return MinioStorageAdapter(get_settings())
