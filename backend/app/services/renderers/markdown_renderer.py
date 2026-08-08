# =============================================================================
# File: markdown_renderer.py
# Module/Service: Report Service (FR9) — Markdown Renderer
# Layer: Service
# Purpose: Render AggregatedReportBlock list into a Markdown file (UC8).
# Responsibilities:
#   - One ``## {title}`` section per block (order preserved as given)
#   - Source-type-specific body: summary/comparison text+bullets; extraction
#     Markdown table or JSON fence; chat_session dialogue lines
#   - Write ``{title}_{report_id}.md`` under report staging path / MinIO key
# Dependencies:
#   - report_aggregation.AggregatedReportBlock; renderers.common
# Public Exports:
#   - render_markdown, MarkdownRenderResult
# Database/Table: N/A (file artifact only; reports.file_path set by Report Service)
# Related Modules: docx_renderer, report_aggregation
# Important Notes: Does not alter AggregatedReportBlock schema; no PDF/DOCX here.
# =============================================================================

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

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
class MarkdownRenderResult:
    """Local staging artifact + MinIO object key for later upload."""

    filename: str
    local_path: Path
    object_key: str
    markdown: str
    section_count: int


def render_markdown(
    blocks: Sequence[AggregatedReportBlock],
    *,
    report_title: str,
    report_id: uuid.UUID,
    workspace_id: uuid.UUID,
    output_dir: Path | None = None,
) -> MarkdownRenderResult:
    """Render blocks to Markdown and write the staging ``.md`` file."""
    filename = build_report_filename(report_title, report_id, extension="md")
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

    parts: list[str] = [f"# {report_title.strip() or 'Report'}", ""]
    for block in blocks:
        parts.append(f"## {block.title}")
        parts.append("")
        body = _render_block_body(block)
        if body:
            parts.append(body)
            parts.append("")

    markdown = "\n".join(parts).rstrip() + "\n"
    ensure_parent_dir(local_path)
    local_path.write_text(markdown, encoding="utf-8")

    return MarkdownRenderResult(
        filename=filename,
        local_path=local_path,
        object_key=object_key,
        markdown=markdown,
        section_count=len(blocks),
    )


def _render_block_body(block: AggregatedReportBlock) -> str:
    source_type = block.source_type
    if isinstance(source_type, str):
        try:
            source_type = ReportSourceType(source_type)
        except ValueError:
            return _json_fence(block.content)

    if source_type is ReportSourceType.summary:
        return _render_summary(block.content)
    if source_type is ReportSourceType.comparison:
        return _render_comparison(block.content)
    if source_type is ReportSourceType.extraction:
        return _render_extraction(block.content)
    if source_type is ReportSourceType.chat_session:
        return _render_chat(block.content)
    return _json_fence(block.content)


def _render_summary(content: dict[str, Any]) -> str:
    lines: list[str] = []
    text = content.get("text")
    if isinstance(text, str) and text.strip():
        lines.append(text.strip())

    sections = content.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = cell_str(section.get("title")).strip()
            body = cell_str(section.get("content")).strip()
            if title:
                lines.append(f"### {title}")
                lines.append("")
            if body:
                lines.append(body)
                lines.append("")

    return "\n".join(lines).rstrip()


def _render_comparison(content: dict[str, Any]) -> str:
    lines: list[str] = []
    similarities = content.get("similarities") or []
    differences = content.get("differences") or []

    if similarities:
        lines.append("### Similarities")
        lines.append("")
        for item in similarities:
            lines.append(f"- {cell_str(item)}")
        lines.append("")

    if differences:
        lines.append("### Differences")
        lines.append("")
        for item in differences:
            lines.append(f"- {cell_str(item)}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _render_extraction(content: dict[str, Any]) -> str:
    table = extraction_as_table(content)
    if table is not None:
        headers, rows = table
        return _markdown_table(headers, rows)

    result = content.get("result")
    payload = result if result is not None else content
    return _json_fence(payload)


def _render_chat(content: dict[str, Any]) -> str:
    messages = content.get("messages") or []
    lines: list[str] = []
    if not isinstance(messages, list):
        return _json_fence(content)

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
        lines.append(f"**{label}:** {text}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers:
        return ""

    def esc(cell: str) -> str:
        return cell.replace("|", "\\|").replace("\n", " ")

    header_line = "| " + " | ".join(esc(h) for h in headers) + " |"
    sep_line = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines = [
        "| " + " | ".join(esc(c) for c in row) + " |" for row in rows
    ]
    return "\n".join([header_line, sep_line, *body_lines])


def _json_fence(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"
