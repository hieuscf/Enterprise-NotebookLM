# =============================================================================
# File: artifacts.py
# Module/Service: Pipeline Worker
# Layer: Adapter
# Purpose: Ephemeral MinIO artifacts passed between pipeline stages (FR2).
# Responsibilities:
#   - Derive `.pipeline/` object keys from document_versions.storage_path
#   - Save/load JSON artifacts (OCR segments → Chunking, …)
# Dependencies:
#   - app.adapters.minio_storage
# Public Exports:
#   - OCR_SEGMENTS_ARTIFACT, pipeline_artifact_key
#   - save_json_artifact, load_json_artifact
# Database/Table: N/A (avoids inter-stage DB round-trips)
# Related Modules: app.workers.stages.ocr_cleaning, chunking (later)
# Important Notes: Artifacts live next to the version file under `.pipeline/`.
# =============================================================================

from __future__ import annotations

import json
from typing import Any

from app.adapters.minio_storage import MinioStorageAdapter

OCR_SEGMENTS_ARTIFACT = "ocr_segments.json"


def pipeline_artifact_key(storage_path: str, artifact_name: str) -> str:
    """Build MinIO key for a stage artifact beside the original file.

    Example:
        ``workspaces/…/v1/report.pdf`` →
        ``workspaces/…/v1/.pipeline/ocr_segments.json``
    """
    if "/" not in storage_path:
        prefix = ""
    else:
        prefix = storage_path.rsplit("/", 1)[0] + "/"
    return f"{prefix}.pipeline/{artifact_name}"


def save_json_artifact(
    storage: MinioStorageAdapter,
    *,
    storage_path: str,
    artifact_name: str,
    payload: dict[str, Any],
) -> str:
    """Serialize ``payload`` to MinIO; return the object key."""
    key = pipeline_artifact_key(storage_path, artifact_name)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    storage.upload_bytes(
        object_key=key,
        data=data,
        content_type="application/json",
    )
    return key


def load_json_artifact(
    storage: MinioStorageAdapter,
    *,
    storage_path: str,
    artifact_name: str,
) -> dict[str, Any]:
    """Load a JSON artifact previously written by a pipeline stage."""
    key = pipeline_artifact_key(storage_path, artifact_name)
    raw = storage.download_bytes(key)
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Artifact '{artifact_name}' must be a JSON object")
    return data
