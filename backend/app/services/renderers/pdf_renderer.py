# =============================================================================
# File: pdf_renderer.py
# Module/Service: Report Service (FR9) — PDF Renderer
# Layer: Service
# Purpose: Convert report Markdown (from markdown_renderer) into a PDF file.
# Responsibilities:
#   - Map Markdown headings / tables / lists / code fences to simple HTML
#   - Lay out HTML via PyMuPDF ``fitz.Story`` (already in stack — no new deps)
#   - Write ``{title}_{report_id}.pdf`` under report staging path / MinIO key
# Dependencies:
#   - pymupdf (fitz); renderers.common path helpers
# Public Exports:
#   - render_pdf, PdfRenderResult, markdown_to_html
# Database/Table: N/A (file artifact only; reports.file_path set by Report Service)
# Related Modules: markdown_renderer (Prompt 2), docx_renderer
# Important Notes:
#   - Input is a Markdown string — reuse Prompt 2 output; do not re-aggregate.
#   - Prefer readable layout over fancy templates; title appears at document start.
# =============================================================================

from __future__ import annotations

import html
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import fitz

from app.services.renderers.common import (
    build_report_filename,
    build_report_object_key,
    ensure_parent_dir,
    resolve_report_staging_path,
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^[-*+]\s+(.*)$")
_FENCE_RE = re.compile(r"^```(\w*)\s*$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_INLINE_RE = re.compile(r"`([^`]+)`")

_PDF_CSS = """
body {
  font-family: Helvetica, Arial, sans-serif;
  font-size: 11pt;
  line-height: 1.45;
  color: #111;
}
h1 { font-size: 20pt; margin: 0 0 16pt 0; }
h2 { font-size: 14pt; margin: 18pt 0 8pt 0; }
h3 { font-size: 12pt; margin: 14pt 0 6pt 0; }
p { margin: 0 0 8pt 0; }
ul { margin: 0 0 10pt 18pt; padding: 0; }
li { margin: 0 0 4pt 0; }
table {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 12pt 0;
  font-size: 10pt;
}
th, td {
  border: 1px solid #444;
  padding: 4pt 6pt;
  text-align: left;
  vertical-align: top;
}
th { background: #eee; font-weight: bold; }
pre {
  background: #f5f5f5;
  border: 1px solid #ccc;
  padding: 8pt;
  font-family: Consolas, Courier New, monospace;
  font-size: 9pt;
  white-space: pre-wrap;
  margin: 0 0 12pt 0;
}
code { font-family: Consolas, Courier New, monospace; font-size: 9pt; }
"""


@dataclass(frozen=True, slots=True)
class PdfRenderResult:
    """Local staging PDF path + MinIO object key for later upload."""

    filename: str
    local_path: Path
    object_key: str


def render_pdf(
    markdown: str,
    *,
    report_title: str,
    report_id: uuid.UUID,
    workspace_id: uuid.UUID,
    output_dir: Path | None = None,
) -> PdfRenderResult:
    """Render a Markdown string to PDF and return the staging file path.

    ``markdown`` should come from ``render_markdown(...).markdown`` (Prompt 2).
    """
    filename = build_report_filename(report_title, report_id, extension="pdf")
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

    body_html = markdown_to_html(markdown or "")
    # Ensure report title is visible at the top even if MD omits H1.
    title = (report_title or "").strip() or "Report"
    if not re.search(r"<h1[\s>]", body_html, flags=re.IGNORECASE):
        body_html = f"<h1>{html.escape(title)}</h1>\n{body_html}"

    full_html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
        f"<style>{_PDF_CSS}</style></head><body>\n"
        f"{body_html}\n</body></html>"
    )

    ensure_parent_dir(local_path)
    _story_html_to_pdf(full_html, local_path)

    return PdfRenderResult(
        filename=filename,
        local_path=local_path,
        object_key=object_key,
    )


def markdown_to_html(markdown: str) -> str:
    """Minimal Markdown → HTML covering report renderer output shapes."""
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i = 0
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    while i < len(lines):
        line = lines[i]
        fence = _FENCE_RE.match(line)
        if fence:
            close_list()
            lang = fence.group(1) or ""
            i += 1
            code_lines: list[str] = []
            while i < len(lines) and not _FENCE_RE.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                i += 1  # closing fence
            code = html.escape("\n".join(code_lines))
            cls = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{code}</code></pre>")
            continue

        if _is_table_header_row(line) and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            close_list()
            table_lines = [line, lines[i + 1]]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            out.append(_table_to_html(table_lines))
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            close_list()
            level = len(heading.group(1))
            text = _inline_to_html(heading.group(2).strip())
            out.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        ul = _UL_RE.match(line)
        if ul:
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline_to_html(ul.group(1).strip())}</li>")
            i += 1
            continue

        if not line.strip():
            close_list()
            i += 1
            continue

        close_list()
        # Merge consecutive paragraph lines
        para_parts = [line.strip()]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if (
                not nxt.strip()
                or _HEADING_RE.match(nxt)
                or _UL_RE.match(nxt)
                or _FENCE_RE.match(nxt)
                or (
                    _is_table_header_row(nxt)
                    and i + 1 < len(lines)
                    and _TABLE_SEP_RE.match(lines[i + 1])
                )
            ):
                break
            para_parts.append(nxt.strip())
            i += 1
        out.append(f"<p>{_inline_to_html(' '.join(para_parts))}</p>")

    close_list()
    return "\n".join(out)


def _story_html_to_pdf(full_html: str, output_path: Path) -> None:
    """Write HTML to PDF using PyMuPDF Story (same stack as preview_generator)."""
    writer = fitz.DocumentWriter(str(output_path))
    try:
        story = fitz.Story(html=full_html)
        mediabox = fitz.paper_rect("a4")
        where = mediabox + (48, 48, -48, -48)  # margins
        more = True
        while more:
            device = writer.begin_page(mediabox)
            more, _ = story.place(where)
            story.draw(device)
            writer.end_page()
    finally:
        writer.close()


def _inline_to_html(text: str) -> str:
    """Escape HTML then restore a small set of Markdown inline markers."""
    escaped = html.escape(text)
    escaped = _BOLD_RE.sub(r"<b>\1</b>", escaped)
    escaped = _CODE_INLINE_RE.sub(r"<code>\1</code>", escaped)
    return escaped


def _is_table_header_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _split_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _table_to_html(table_lines: list[str]) -> str:
    if len(table_lines) < 2:
        return ""
    headers = _split_table_row(table_lines[0])
    body_rows = [_split_table_row(row) for row in table_lines[2:]]
    parts = ["<table>", "<thead><tr>"]
    for h in headers:
        parts.append(f"<th>{_inline_to_html(h)}</th>")
    parts.append("</tr></thead><tbody>")
    for row in body_rows:
        # Pad / trim to header width
        cells = list(row) + [""] * max(0, len(headers) - len(row))
        parts.append("<tr>")
        for cell in cells[: len(headers)]:
            parts.append(f"<td>{_inline_to_html(cell)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)
