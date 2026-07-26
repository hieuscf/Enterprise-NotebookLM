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
#   - MinioStorageAdapter, get_minio_storage
# Database/Table: N/A (paths stored on document_versions.storage_path)
# Related Modules: app.services.documents, app.workers.pipeline
# Important Notes: documents table never stores file bytes — only storage_path on versions.
# =============================================================================

from __future__ import annotations

import io
from functools import lru_cache
from typing import Any

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings, get_settings


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
        response = self._client.get_object(self._bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete_object(self, object_key: str) -> None:
        try:
            self._client.remove_object(self._bucket, object_key)
        except S3Error:
            # Best-effort cleanup — missing object is not fatal for delete flows.
            return


@lru_cache
def get_minio_storage() -> MinioStorageAdapter:
    return MinioStorageAdapter(get_settings())
