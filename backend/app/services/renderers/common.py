# =============================================================================
# File: common.py
# Module/Service: Report Service (FR9) — Renderers
# Layer: Service
# Purpose: Shared helpers for Markdown/DOCX report renderers (paths + tables).
# Responsibilities:
#   - Sanitize report filenames; build MinIO-style object keys + staging paths
#   - Detect tabular extraction payloads (headers + rows)
# Dependencies:
#   - AggregatedReportBlock (read-only)
# Public Exports:
#   - build_report_filename, build_report_object_key, resolve_report_staging_path,
#     ensure_parent_dir, extraction_as_table, cell_str
# Database/Table: N/A
# Related Modules: markdown_renderer, docx_renderer; documents.build_storage_path
# Important Notes:
#   - Object key mirrors ingest convention:
#     workspaces/{workspaceId}/reports/{reportId}/{filename}
# =============================================================================

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path
from typing import Any


_UNSAFE_FILENAME_RE = re.compile(r"[^\w\-.]+", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def build_report_filename(
    report_title: str,
    report_id: uuid.UUID,
    *,
    extension: str,
) -> str:
    """Build ``{safe_title}_{report_id}.{ext}`` (no path separators)."""
    ext = extension.lstrip(".").lower()
    raw = (report_title or "").strip() or "report"
    safe = _UNSAFE_FILENAME_RE.sub("_", raw)
    safe = _WHITESPACE_RE.sub("_", safe).strip("._") or "report"
    # Avoid overly long object keys / Windows path limits.
    safe = safe[:120]
    return f"{safe}_{report_id}.{ext}"


def build_report_object_key(
    *,
    workspace_id: uuid.UUID,
    report_id: uuid.UUID,
    filename: str,
) -> str:
    """MinIO key: workspaces/{workspaceId}/reports/{reportId}/{filename}."""
    safe_name = filename.replace("/", "_").replace("\\", "_")
    return f"workspaces/{workspace_id}/reports/{report_id}/{safe_name}"


def resolve_report_staging_path(
    *,
    workspace_id: uuid.UUID,
    report_id: uuid.UUID,
    filename: str,
    output_dir: Path | None = None,
) -> Path:
    """Local staging path mirroring the MinIO object key layout."""
    root = output_dir or (
        Path(tempfile.gettempdir()) / "enterprise-notebooklm" / "reports"
    )
    return (
        root
        / "workspaces"
        / str(workspace_id)
        / "reports"
        / str(report_id)
        / filename
    )


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def cell_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def extraction_as_table(content: dict[str, Any]) -> tuple[list[str], list[list[str]]] | None:
    """Return (headers, rows) when extraction payload is tabular; else None.

    Recognizes:
    - ``extraction_type == "table"`` with ``result.headers`` + ``result.rows``
    - Any ``result`` dict that already has non-empty ``headers`` + list ``rows``
    """
    result = content.get("result")
    extraction_type = content.get("extraction_type")
    if not isinstance(result, dict):
        return None

    headers_raw = result.get("headers")
    rows_raw = result.get("rows")
    is_explicit_table = extraction_type == "table"
    has_shape = isinstance(headers_raw, list) and isinstance(rows_raw, list)

    if not (is_explicit_table or has_shape):
        return None
    if not has_shape or not headers_raw:
        return None

    headers = [cell_str(h) for h in headers_raw]
    rows: list[list[str]] = []
    for row in rows_raw:
        if isinstance(row, dict):
            rows.append([cell_str(row.get(h)) for h in headers_raw])
        elif isinstance(row, (list, tuple)):
            cells = [cell_str(v) for v in row]
            # Pad / trim to header width
            if len(cells) < len(headers):
                cells.extend([""] * (len(headers) - len(cells)))
            rows.append(cells[: len(headers)])
        else:
            rows.append([cell_str(row)] + [""] * (len(headers) - 1))
    return headers, rows
