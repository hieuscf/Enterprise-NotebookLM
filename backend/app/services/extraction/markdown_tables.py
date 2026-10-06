# =============================================================================
# File: markdown_tables.py
# Module/Service: Extraction Service (FR7)
# Layer: Service
# Purpose: Deterministic parsers for original document tables (GFM + HTML cells).
# Responsibilities:
#   - Parse GFM pipe tables from chunk content
#   - Reconstruct tables from LlamaParse-flattened <th>/<td> sequences
#   - Decode entities; strip nested markup inside cells
# Dependencies:
#   - html, re (stdlib only)
# Public Exports:
#   - parse_document_table, looks_like_document_table,
#     parse_markdown_table, looks_like_markdown_table,
#     parse_html_cell_table, looks_like_html_cell_table
# Database/Table: N/A
# Related Modules: extraction_service table gallery path
# Important Notes: Used for extraction_type=table (0 LLM). Does not invent facts.
#   LlamaParse often emits bare <th>/<td> lines without <table>/<tr>.
# =============================================================================

from __future__ import annotations

import html
import re
from typing import Any

_TABLE_DELIM_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
_PIPE_ROW_RE = re.compile(r"\|")
_HTML_CELL_RE = re.compile(
    r"<(th|td)(?:\s[^>]*)?>\s*(.*?)\s*</\1>",
    flags=re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def looks_like_document_table(text: str) -> bool:
    return looks_like_markdown_table(text) or looks_like_html_cell_table(text)


def parse_document_table(text: str) -> dict[str, Any] | None:
    """Parse the best-effort table representation from chunk text."""
    parsed = parse_markdown_table(text)
    if parsed is not None:
        return parsed
    return parse_html_cell_table(text)


def looks_like_markdown_table(text: str) -> bool:
    """True when content has at least a header row + delimiter row."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    return bool(_PIPE_ROW_RE.search(lines[0]) and _TABLE_DELIM_RE.match(lines[1]))


def parse_markdown_table(text: str) -> dict[str, Any] | None:
    """Parse a GFM pipe table into ``{headers, rows}`` (rows as dicts)."""
    raw_lines = (text or "").splitlines()
    lines = [ln.rstrip() for ln in raw_lines if ln.strip()]
    if len(lines) < 2:
        return None
    if not _PIPE_ROW_RE.search(lines[0]) or not _TABLE_DELIM_RE.match(lines[1]):
        return None

    headers = _split_row(lines[0])
    if not headers:
        return None
    headers = _unique_headers(headers)

    rows: list[dict[str, Any]] = []
    for line in lines[2:]:
        if _TABLE_DELIM_RE.match(line):
            continue
        if not _PIPE_ROW_RE.search(line):
            continue
        cells = _split_row(line)
        while len(cells) < len(headers):
            cells.append("")
        cells = cells[: len(headers)]
        rows.append({headers[i]: cells[i] for i in range(len(headers))})

    return {"headers": headers, "rows": rows}


def looks_like_html_cell_table(text: str) -> bool:
    """True when content has enough <th>/<td> cells to form a table."""
    return len(_HTML_CELL_RE.findall(text or "")) >= 2


def parse_html_cell_table(text: str) -> dict[str, Any] | None:
    """Rebuild a table from flattened LlamaParse ``<th>/<td>`` sequences.

    Typical shapes:
      - ``<th>A</th><th>B</th><td>…</td><td>…</td>…`` (N headers, then body)
      - ``<th>A</th><td>label</td><td>value</td>…`` (1 header → promote to 2 cols)
      - only ``<td>`` cells → first row becomes headers
    """
    cells = [
        (tag.lower(), _clean_cell_html(inner))
        for tag, inner in _HTML_CELL_RE.findall(text or "")
    ]
    if len(cells) < 2:
        return None

    headers: list[str] = []
    body: list[str] = []
    for tag, value in cells:
        if tag == "th" and not body:
            headers.append(value)
        else:
            body.append(value)

    if headers:
        width = len(headers)
        # Single leading <th> with paired body cells → 2-column label/value table.
        if width == 1 and len(body) >= 2 and len(body) % 2 == 0:
            headers = _unique_headers([headers[0], "Chi tiết"])
            width = 2
        else:
            headers = _unique_headers(headers)
            width = len(headers)
    else:
        width = _infer_width(len(body))
        if width < 1 or len(body) < width:
            return None
        headers = _unique_headers(body[:width])
        body = body[width:]

    if width < 1:
        return None

    rows: list[dict[str, Any]] = []
    for i in range(0, len(body), width):
        chunk = body[i : i + width]
        if not chunk:
            continue
        while len(chunk) < width:
            chunk.append("")
        rows.append({headers[j]: chunk[j] for j in range(width)})

    # Require at least one data row OR keep header-only tables.
    return {"headers": headers, "rows": rows}


def _clean_cell_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = _TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _infer_width(cell_count: int) -> int:
    """Pick a plausible column count when headers are missing."""
    if cell_count < 2:
        return 0
    for width in (2, 3, 4, 5):
        if cell_count % width == 0 and cell_count // width >= 2:
            return width
    for width in (2, 3, 4):
        if cell_count > width:
            return width
    return cell_count


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _unique_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for raw in headers:
        base = (raw or "").strip() or "Column"
        count = seen.get(base, 0)
        seen[base] = count + 1
        out.append(base if count == 0 else f"{base}_{count + 1}")
    return out
