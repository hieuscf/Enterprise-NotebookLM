# =============================================================================
# File: export.py
# Module/Service: Report Service (FR9 / TASK-CMP-26)
# Layer: Service
# Purpose: Deterministic helpers for secure Comparison Report artifact delivery.
# Responsibilities:
#   - Map export_format → MIME type / extension
#   - Sanitize download filenames; build RFC 5987 Content-Disposition
#   - Validate stored object keys belong to the requested report/workspace
# Dependencies:
#   - app.models.enums.ReportFormat
# Public Exports:
#   - EXPORT_CONTENT_TYPES, export_extension, sanitize_export_filename,
#     content_disposition_attachment, resolve_export_format,
#     artifact_key_is_owned
# Database/Table: reports (read metadata only)
# Related Modules: report_service.export_report, app.api.reports
# Important Notes:
#   - Delivery only. Never regenerate, remap, or call an LLM.
#   - file_path is an internal object key — never a public URL.
# =============================================================================

from __future__ import annotations

import re
from urllib.parse import quote

from app.models.enums import ReportFormat

EXPORT_CONTENT_TYPES: dict[ReportFormat, str] = {
    ReportFormat.pdf: "application/pdf",
    ReportFormat.docx: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ReportFormat.markdown: "text/markdown; charset=utf-8",
}

EXPORT_EXTENSIONS: dict[ReportFormat, str] = {
    ReportFormat.pdf: "pdf",
    ReportFormat.docx: "docx",
    ReportFormat.markdown: "md",
}

_UNSAFE_FILENAME_RE = re.compile(r"[^\w\-.]+", re.UNICODE)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_STEM = 120


def resolve_export_format(value: object) -> ReportFormat | None:
    """Return a known ReportFormat or None. Do not guess from filenames."""
    if isinstance(value, ReportFormat):
        return value
    raw = getattr(value, "value", value)
    try:
        return ReportFormat(str(raw))
    except (TypeError, ValueError):
        return None


def export_extension(fmt: ReportFormat) -> str:
    return EXPORT_EXTENSIONS[fmt]


def export_content_type(fmt: ReportFormat) -> str:
    return EXPORT_CONTENT_TYPES[fmt]


def sanitize_export_filename(title: str | None, fmt: ReportFormat) -> str:
    """Build a download name from the report title. Never trust raw titles."""
    ext = export_extension(fmt)
    raw = _CONTROL_RE.sub("", (title or "").strip()) or "report"
    raw = raw.replace("\\", "-").replace("/", "-")
    raw = raw.replace(":", " ").replace("*", " ").replace("?", " ")
    raw = raw.replace('"', " ").replace("<", " ").replace(">", " ").replace("|", " ")
    while ".." in raw:
        raw = raw.replace("..", ".")
    safe = _UNSAFE_FILENAME_RE.sub("_", raw)
    safe = re.sub(r"_+", "_", safe).strip("._") or "report"
    safe = safe[:_MAX_STEM].rstrip("._") or "report"
    return f"{safe}.{ext}"


def _ascii_fallback(filename: str) -> str:
    ascii_name = filename.encode("ascii", "replace").decode("ascii")
    ascii_name = ascii_name.replace("?", "_").replace("\\", "_").replace('"', "")
    ascii_name = ascii_name.replace("/", "-").replace(":", "-")
    stem, dot, ext = ascii_name.rpartition(".")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._") or "report"
    ext = re.sub(r"[^A-Za-z0-9]+", "", ext) or "bin"
    return f"{stem}.{ext}" if dot else stem


def content_disposition_attachment(filename: str) -> str:
    """RFC 6266 / 5987 attachment header. ASCII filename + UTF-8 filename*."""
    ascii_name = _ascii_fallback(filename)
    encoded = quote(filename, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'


def artifact_key_is_owned(
    file_path: str | None,
    *,
    workspace_id: object,
    report_id: object,
) -> bool:
    """True only when file_path is this report's object key (not a URL)."""
    if not file_path or not isinstance(file_path, str):
        return False
    key = file_path.strip()
    if not key:
        return False
    lowered = key.lower()
    if "://" in key or lowered.startswith("s3://") or lowered.startswith("minio://"):
        return False
    if any(token in key for token in ("..", "\\", "\x00")):
        return False
    expected = f"workspaces/{workspace_id}/reports/{report_id}/"
    if not key.startswith(expected):
        return False
    rest = key[len(expected) :]
    return bool(rest) and "/" not in rest and rest not in {".", ".."}
