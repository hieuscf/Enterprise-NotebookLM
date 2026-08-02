# =============================================================================
# File: templates.py
# Module/Service: Query Router — Metadata Branch (FR11)
# Layer: Service
# Purpose: Simple string templates for metadata answers (0 LLM / no generation).
# Responsibilities:
#   - Render named templates with format kwargs
# Dependencies:
#   - stdlib
# Public Exports:
#   - render_template, METADATA_TEMPLATES
# Database/Table: N/A
# Related Modules: handlers.metadata_handler, metadata_registry
# Important Notes: Never call LLM; missing keys raise KeyError intentionally.
# =============================================================================

from __future__ import annotations

METADATA_TEMPLATES: dict[str, str] = {
    "count_documents_vi": "Có {count} tài liệu trong workspace.",
    "count_documents_en": "Workspace currently contains {count} documents.",
    "count_files_vi": "Có {count} file trong workspace.",
    "count_files_en": "Workspace currently contains {count} files.",
    "count_pdf_vi": "Có {count} tài liệu PDF trong workspace.",
    "count_pdf_en": "Workspace currently contains {count} PDF documents.",
    "count_by_type_vi": "Có {count} tài liệu {file_type} trong workspace.",
    "count_by_type_en": "Workspace currently contains {count} {file_type} documents.",
    "list_documents_vi": "Danh sách tài liệu ({count}): {preview}{more}.",
    "list_documents_en": "Documents ({count}): {preview}{more}.",
    "list_by_type_vi": "Tài liệu {file_type} ({count}): {preview}{more}.",
    "list_by_type_en": "{file_type} documents ({count}): {preview}{more}.",
    "latest_documents_vi": "Tài liệu mới nhất ({count}): {preview}{more}.",
    "latest_documents_en": "Latest documents ({count}): {preview}{more}.",
    "oldest_documents_vi": "Tài liệu cũ nhất ({count}): {preview}{more}.",
    "oldest_documents_en": "Oldest documents ({count}): {preview}{more}.",
    "count_members_vi": "Workspace có {count} thành viên.",
    "count_members_en": "Workspace has {count} members.",
    "stats_file_type_vi": "Thống kê theo loại file — {summary}.",
    "stats_file_type_en": "File type statistics — {summary}.",
    "document_owner_vi": "Người upload: {owner_id} (tài liệu: {title}).",
    "document_owner_en": "Uploaded by: {owner_id} (document: {title}).",
    "document_owner_unknown_vi": "Không xác định được người upload.",
    "document_owner_unknown_en": "Uploader could not be determined.",
    "empty_list_vi": "{prefix}: không có kết quả.",
    "empty_list_en": "{prefix}: no results.",
    "count_chunks_vi": "Workspace có {count} chunk.",
    "count_chunks_en": "Workspace contains {count} chunks.",
    "count_pages_vi": "Workspace có khoảng {count} trang tài liệu.",
    "count_pages_en": "Workspace has approximately {count} document pages.",
}


def render_template(template_key: str, **kwargs: object) -> str:
    """Render a named metadata template.

    Args:
        template_key: Key in ``METADATA_TEMPLATES``.
        **kwargs: Format fields required by the template.

    Returns:
        Filled template string.

    Raises:
        KeyError: Unknown template key.
    """
    template = METADATA_TEMPLATES[template_key]
    return template.format(**kwargs)


def list_preview(titles: list[str], *, max_items: int = 5) -> tuple[str, str, int]:
    """Build preview / more-suffix / count for list templates.

    Returns:
        ``(preview, more_suffix, count)``.
    """
    count = len(titles)
    if count == 0:
        return "", "", 0
    preview = ", ".join(titles[:max_items])
    more = "" if count <= max_items else f" (và {count - max_items} nữa)"
    return preview, more, count
