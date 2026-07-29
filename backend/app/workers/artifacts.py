# =============================================================================
# File: artifacts.py
# Module/Service: Pipeline Worker
# Layer: Adapter
# Purpose: MinIO artifacts derived from a document version — inter-stage handoff
#   plus durable outputs such as the LlamaParse Markdown (FR2).
# Responsibilities:
#   - Derive `.pipeline/` object keys from document_versions.storage_path
#   - Save/load JSON artifacts (Layout Analysis, …)
#   - Save durable text outputs beside the original file (Markdown)
# Dependencies:
#   - app.adapters.minio_storage
# Public Exports:
#   - LAYOUT_ARTIFACT, MARKDOWN_ARTIFACT
#   - pipeline_artifact_key, version_output_key
#   - save_json_artifact, load_json_artifact, save_text_output
# Database/Table: document_versions.markdown_storage_path (Markdown key)
# Related Modules: app.workers.stages.document_understanding
# Important Notes:
#   - `.pipeline/` holds ephemeral inter-stage handoffs, safe to delete/rebuild.
#   - version_output_key() holds durable outputs referenced by DB columns.
# =============================================================================

from __future__ import annotations

import json
from typing import Any

from app.adapters.minio_storage import MinioStorageAdapter

#: Full Layout Analysis incl. block text (v3 document_understanding stage).
LAYOUT_ARTIFACT = "llamaparse_layout.json"
#: Markdown output name; the key itself goes to document_versions.markdown_storage_path.
MARKDOWN_ARTIFACT = "document.md"


def pipeline_artifact_key(storage_path: str, artifact_name: str) -> str:
    """Build MinIO key for a stage artifact beside the original file.

    Example:
        ``workspaces/…/v1/report.pdf`` →
        ``workspaces/…/v1/.pipeline/llamaparse_layout.json``
    """
    return f"{_version_prefix(storage_path)}.pipeline/{artifact_name}"


def version_output_key(storage_path: str, output_name: str) -> str:
    """Build MinIO key for a durable derived output of the same version.

    Example:
        ``workspaces/…/v1/report.pdf`` → ``workspaces/…/v1/document.md``
    """
    return f"{_version_prefix(storage_path)}{output_name}"


def _version_prefix(storage_path: str) -> str:
    if "/" not in storage_path:
        return ""
    return storage_path.rsplit("/", 1)[0] + "/"


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


def save_text_output(
    storage: MinioStorageAdapter,
    *,
    storage_path: str,
    output_name: str,
    text: str,
    content_type: str = "text/markdown; charset=utf-8",
) -> str:
    """Store a durable text output beside the version file; return the key."""
    key = version_output_key(storage_path, output_name)
    storage.upload_bytes(
        object_key=key,
        data=text.encode("utf-8"),
        content_type=content_type,
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
