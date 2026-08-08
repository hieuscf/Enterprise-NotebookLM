# =============================================================================
# File: docx_renderer.py
# Module/Service: Report Service (FR9) — DOCX Renderer
# Layer: Service
# Purpose: Render AggregatedReportBlock list into a Word ``.docx`` file (UC8).
# Responsibilities:
#   - Heading styles per block title; body by source_type (mirrors Markdown logic)
#   - Real Word tables for tabular extractions (not screenshots / images)
#   - Write ``{title}_{report_id}.docx`` under report staging path / MinIO key
# Dependencies:
#   - python-docx; report_aggregation.AggregatedReportBlock; renderers.common
# Public Exports:
#   - render_docx, DocxRenderResult
# Database/Table: N/A (file artifact only; reports.file_path set by Report Service)
# Related Modules: markdown_renderer, report_aggregation, app.ai.ocr.docx_parser
# Important Notes:
#   - Reuses project python-docx dependency (no separate docx-helper skill).
#   - Does not alter AggregatedReportBlock schema; no Markdown/PDF here.
# =============================================================================

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from docx import Document
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.models.enums import ReportSourceType
from app.services.report_aggregation import AggregatedReportBlock
from app.services.renderers.common import (
    build_report_filename,
    build_report_object_key,
    cell_str,
    ensure_parent_dir,
    extraction_as_table,
    resolve_report_staging_path,
)


@dataclass(frozen=True, slots=True)
class DocxRenderResult:
    """Local staging artifact + MinIO object key for later upload."""

    filename: str
    local_path: Path
    object_key: str
    section_count: int


def render_docx(
    blocks: Sequence[AggregatedReportBlock],
    *,
    report_title: str,
    report_id: uuid.UUID,
    workspace_id: uuid.UUID,
    output_dir: Path | None = None,
) -> DocxRenderResult:
    """Render blocks to DOCX and write the staging ``.docx`` file."""
    filename = build_report_filename(report_title, report_id, extension="docx")
    object_key = build_report_object_key(
        workspace_id=workspace_id,
        report_id=report_id,
        filename=filename,
    )
    local_path = resolve_report_staging_path(
        workspace_id=workspace_id,
        report_id=report_id,
        filename=filename,
        output_dir=output_dir,
    )

    document = Document()
    title = report_title.strip() or "Report"
    heading = document.add_heading(title, level=0)
    heading.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT

    for block in blocks:
        document.add_heading(block.title, level=1)
        _append_block_body(document, block)

    ensure_parent_dir(local_path)
    document.save(str(local_path))

    return DocxRenderResult(
        filename=filename,
        local_path=local_path,
        object_key=object_key,
        section_count=len(blocks),
    )


def _append_block_body(document: Document, block: AggregatedReportBlock) -> None:
    source_type = block.source_type
    if isinstance(source_type, str):
        try:
            source_type = ReportSourceType(source_type)
        except ValueError:
            _add_preformatted(document, json.dumps(block.content, ensure_ascii=False, indent=2))
            return

    if source_type is ReportSourceType.summary:
        _append_summary(document, block.content)
    elif source_type is ReportSourceType.comparison:
        _append_comparison(document, block.content)
    elif source_type is ReportSourceType.extraction:
        _append_extraction(document, block.content)
    elif source_type is ReportSourceType.chat_session:
        _append_chat(document, block.content)
    else:
        _add_preformatted(document, json.dumps(block.content, ensure_ascii=False, indent=2))


def _append_summary(document: Document, content: dict[str, Any]) -> None:
    text = content.get("text")
    if isinstance(text, str) and text.strip():
        document.add_paragraph(text.strip())

    sections = content.get("sections")
    if not isinstance(sections, list):
        return
    for section in sections:
        if not isinstance(section, dict):
            continue
        title = cell_str(section.get("title")).strip()
        body = cell_str(section.get("content")).strip()
        if title:
            document.add_heading(title, level=2)
        if body:
            document.add_paragraph(body)


def _append_comparison(document: Document, content: dict[str, Any]) -> None:
    similarities = content.get("similarities") or []
    differences = content.get("differences") or []

    if similarities:
        document.add_heading("Similarities", level=2)
        for item in similarities:
            document.add_paragraph(cell_str(item), style="List Bullet")

    if differences:
        document.add_heading("Differences", level=2)
        for item in differences:
            document.add_paragraph(cell_str(item), style="List Bullet")


def _append_extraction(document: Document, content: dict[str, Any]) -> None:
    table = extraction_as_table(content)
    if table is not None:
        headers, rows = table
        _add_table(document, headers, rows)
        return

    result = content.get("result")
    payload = result if result is not None else content
    _add_preformatted(document, json.dumps(payload, ensure_ascii=False, indent=2))


def _append_chat(document: Document, content: dict[str, Any]) -> None:
    messages = content.get("messages") or []
    if not isinstance(messages, list):
        _add_preformatted(document, json.dumps(content, ensure_ascii=False, indent=2))
        return

    for message in messages:
        if not isinstance(message, dict):
            continue
        role = cell_str(message.get("role")).strip().lower()
        text = cell_str(message.get("content")).strip()
        if role == "user":
            label = "User"
        elif role == "assistant":
            label = "Assistant"
        else:
            label = role.title() or "Message"
        paragraph = document.add_paragraph()
        run = paragraph.add_run(f"{label}: ")
        run.bold = True
        paragraph.add_run(text)


def _add_table(document: Document, headers: list[str], rows: list[list[str]]) -> Table:
    table = document.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    header_cells = table.rows[0].cells
    for idx, header in enumerate(headers):
        header_cells[idx].text = header
        for paragraph in header_cells[idx].paragraphs:
            for run in paragraph.runs:
                run.bold = True

    for row_idx, row in enumerate(rows):
        cells = table.rows[row_idx + 1].cells
        for col_idx, value in enumerate(row):
            cells[col_idx].text = value
    return table


def _add_preformatted(document: Document, text: str) -> Paragraph:
    """Monospace-ish paragraph for JSON payloads (no screenshot tables)."""
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.font.name = "Consolas"
    return paragraph
