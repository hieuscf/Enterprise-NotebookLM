# =============================================================================
# File: layout.py
# Module/Service: Pipeline Worker — Document Understanding ([AI])
# Layer: Service
# Purpose: Turn LlamaParse output into Layout Analysis + Metadata Extraction for
#   document_versions.layout_metadata and pipeline_stage_logs.metadata (FR2 v3).
# Responsibilities:
#   - Metadata Extraction from the Markdown structure itself (headings per level,
#     tables, figures, word count) — no extra API call
#   - Build ordered layout blocks + nested heading tree from the items tree,
#     falling back to Markdown parsing when items are unavailable
#   - Emit the interim OCR-segment shape consumed by stage_chunking
# Dependencies:
#   - stdlib only (no LlamaIndex / LangChain), app.models.enums.FileType
# Public Exports:
#   - MarkdownMetrics, LayoutBlock, LayoutAnalysis
#   - extract_markdown_metrics, build_layout_analysis
#   - build_layout_metadata, build_layout_artifact, build_ocr_segments
# Database/Table: document_versions.layout_metadata (JSONB) — shape defined here
# Related Modules: app.workers.stages.document_understanding, app.ai.chunking
# Important Notes:
#   - Pure functions only: no HTTP, no DB, no object storage — keeps the mapping
#     unit-testable without a LlamaParse key.
#   - build_layout_metadata() deliberately omits block text so the JSONB column
#     stays small; full text lives in the MinIO layout artifact.
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.models.enums import FileType

#: Formats where a page number is physically meaningful. DOCX/TXT use
#: section_index instead — inventing page numbers there would make Citation
#: (FR5) report a "trang X" that does not exist.
PAGINATED_FILE_TYPES = frozenset({FileType.pdf, FileType.pptx, FileType.xlsx})

BLOCK_HEADING = "heading"
BLOCK_PARAGRAPH = "paragraph"
BLOCK_TABLE = "table"
BLOCK_LIST = "list"
BLOCK_FIGURE = "figure"

#: LlamaParse item type → our layout_type vocabulary (see database design §1).
_ITEM_TYPE_MAP: dict[str, str] = {
    "heading": BLOCK_HEADING,
    "title": BLOCK_HEADING,
    "section_header": BLOCK_HEADING,
    "table": BLOCK_TABLE,
    "figure": BLOCK_FIGURE,
    "image": BLOCK_FIGURE,
    "chart": BLOCK_FIGURE,
    "list": BLOCK_LIST,
    "list_item": BLOCK_LIST,
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|?\s*$")
_TABLE_DELIMITER_RE = re.compile(r"^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_IMAGE_ONLY_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")
_WORD_RE = re.compile(r"[^\W_]+(?:['\u2019-][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True, slots=True)
class MarkdownMetrics:
    """Metadata Extraction results derived from the Markdown structure.

    Attributes:
        heading_counts_by_level: Heading count keyed by level 1–6.
        heading_count: Total headings across all levels.
        table_count: Markdown tables (header + delimiter row detected).
        figure_count: Markdown image references.
        word_count: Word-like tokens across the whole document.
        char_count: Raw Markdown length in characters.
    """

    heading_counts_by_level: dict[int, int]
    heading_count: int
    table_count: int
    figure_count: int
    word_count: int
    char_count: int

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe form (JSONB keys must be strings)."""
        return {
            "heading_counts_by_level": {
                str(level): count for level, count in sorted(self.heading_counts_by_level.items())
            },
            "heading_count": self.heading_count,
            "table_count": self.table_count,
            "figure_count": self.figure_count,
            "word_count": self.word_count,
            "char_count": self.char_count,
        }


@dataclass(frozen=True, slots=True)
class LayoutBlock:
    """One positioned content block in reading order.

    Attributes:
        order_index: Zero-based reading order across the whole document.
        block_type: One of paragraph / heading / table / list / figure.
        text: Block text (Markdown for tables).
        page_number: Source page when LlamaParse reported one.
        heading_level: 1–6 for headings, None otherwise.
        heading_path: Breadcrumb of enclosing headings, " > " separated.
        depth: Depth in the heading hierarchy (0 = above any heading).
        bbox: Bounding box as [x, y, w, h] when the parser provided it.
        row_count: Table rows (tables only).
        col_count: Table columns (tables only).
    """

    order_index: int
    block_type: str
    text: str
    page_number: int | None = None
    heading_level: int | None = None
    heading_path: str | None = None
    depth: int = 0
    bbox: list[float] | None = None
    row_count: int | None = None
    col_count: int | None = None

    def as_summary(self) -> dict[str, Any]:
        """Positional summary without text — for the layout_metadata column."""
        payload: dict[str, Any] = {
            "order_index": self.order_index,
            "block_type": self.block_type,
            "depth": self.depth,
            "char_count": len(self.text),
        }
        optional = {
            "page_number": self.page_number,
            "heading_level": self.heading_level,
            "heading_path": self.heading_path,
            "bbox": self.bbox,
            "row_count": self.row_count,
            "col_count": self.col_count,
        }
        payload.update({k: v for k, v in optional.items() if v is not None})
        return payload

    def as_dict(self) -> dict[str, Any]:
        """Full form including text — for the MinIO layout artifact."""
        return {**self.as_summary(), "text": self.text}


@dataclass(frozen=True, slots=True)
class LayoutAnalysis:
    """Structured Layout Analysis for one document version.

    Attributes:
        blocks: Ordered layout blocks.
        heading_tree: Nested heading nodes (roots first).
        page_count: Pages reported by the parser (0 when unpaginated).
        section_count: Distinct top-level sections, used as the logical page
            count for formats without physical pages.
        source: ``items`` when built from the parser tree, ``markdown`` when
            reconstructed from the Markdown text.
    """

    blocks: list[LayoutBlock] = field(default_factory=list)
    heading_tree: list[dict[str, Any]] = field(default_factory=list)
    page_count: int = 0
    section_count: int = 0
    source: str = "markdown"


# ---------------------------------------------------------------------------
# Metadata Extraction — from the Markdown structure itself (no extra API call)
# ---------------------------------------------------------------------------


def extract_markdown_metrics(markdown: str) -> MarkdownMetrics:
    """Count headings per level, tables, figures and words in Markdown.

    Fenced code blocks are skipped for structure detection so that ``#`` inside
    a code sample is not mistaken for a heading.

    Args:
        markdown: Full-document Markdown from the parser.

    Returns:
        Counts written to ``pipeline_stage_logs.metadata``.
    """
    lines = markdown.splitlines()
    heading_counts: dict[int, int] = {}
    table_count = 0
    figure_count = 0

    in_fence = False
    index = 0
    while index < len(lines):
        line = lines[index]
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence:
            index += 1
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            heading_counts[level] = heading_counts.get(level, 0) + 1
            index += 1
            continue

        if _is_table_start(lines, index):
            table_count += 1
            index = _skip_table(lines, index)
            continue

        figure_count += len(_IMAGE_RE.findall(line))
        index += 1

    return MarkdownMetrics(
        heading_counts_by_level=heading_counts,
        heading_count=sum(heading_counts.values()),
        table_count=table_count,
        figure_count=figure_count,
        word_count=len(_WORD_RE.findall(markdown)),
        char_count=len(markdown),
    )


def _is_table_start(lines: list[str], index: int) -> bool:
    """A Markdown table = a pipe row immediately followed by a delimiter row."""
    if not _TABLE_ROW_RE.match(lines[index]):
        return False
    nxt = index + 1
    return (
        nxt < len(lines)
        and _TABLE_ROW_RE.match(lines[nxt]) is not None
        and _TABLE_DELIMITER_RE.match(lines[nxt]) is not None
    )


def _skip_table(lines: list[str], index: int) -> int:
    cursor = index
    while cursor < len(lines) and _TABLE_ROW_RE.match(lines[cursor]):
        cursor += 1
    return cursor


# ---------------------------------------------------------------------------
# Layout Analysis
# ---------------------------------------------------------------------------


def build_layout_analysis(
    *,
    markdown: str,
    item_pages: list[dict[str, Any]] | None = None,
    reported_page_count: int = 0,
) -> LayoutAnalysis:
    """Build ordered blocks + heading tree from the parser output.

    Prefers the LlamaParse items tree (carries page numbers and bounding boxes);
    falls back to parsing the Markdown when items are absent — e.g. a tier that
    does not return them.

    Args:
        markdown: Full-document Markdown.
        item_pages: ``items.pages`` from the parse result.
        reported_page_count: Page count the parser reported, if any.

    Returns:
        Layout Analysis for ``document_versions.layout_metadata``.
    """
    if item_pages:
        blocks = _blocks_from_items(item_pages)
        source = "items"
    else:
        blocks = _blocks_from_markdown(markdown)
        source = "markdown"

    page_numbers = {b.page_number for b in blocks if b.page_number is not None}
    page_count = reported_page_count or (max(page_numbers) if page_numbers else 0)
    top_level = _top_level_section_count(blocks)

    return LayoutAnalysis(
        blocks=blocks,
        heading_tree=_build_heading_tree(blocks),
        page_count=page_count,
        section_count=top_level,
        source=source,
    )


def _blocks_from_items(item_pages: list[dict[str, Any]]) -> list[LayoutBlock]:
    blocks: list[LayoutBlock] = []
    stack: list[tuple[int, str]] = []

    for page in item_pages:
        page_number = _coerce_page_number(page)
        for item in page.get("items") or []:
            if not isinstance(item, dict):
                continue
            block_type = _ITEM_TYPE_MAP.get(str(item.get("type") or "").lower(), BLOCK_PARAGRAPH)
            text = _item_text(item, block_type)
            if not text.strip() and block_type != BLOCK_FIGURE:
                continue

            if block_type == BLOCK_HEADING:
                level = _coerce_level(item)
                stack = _push_heading(stack, level, text)
                blocks.append(
                    LayoutBlock(
                        order_index=len(blocks),
                        block_type=BLOCK_HEADING,
                        text=text,
                        page_number=page_number,
                        heading_level=level,
                        heading_path=_join_path(stack),
                        depth=max(0, level - 1),
                        bbox=_coerce_bbox(item),
                    )
                )
                continue

            row_count, col_count = _table_shape(item) if block_type == BLOCK_TABLE else (None, None)
            blocks.append(
                LayoutBlock(
                    order_index=len(blocks),
                    block_type=block_type,
                    text=text,
                    page_number=page_number,
                    heading_path=_join_path(stack),
                    depth=len(stack),
                    bbox=_coerce_bbox(item),
                    row_count=row_count,
                    col_count=col_count,
                )
            )
    return blocks


def _blocks_from_markdown(markdown: str) -> list[LayoutBlock]:
    lines = markdown.splitlines()
    blocks: list[LayoutBlock] = []
    stack: list[tuple[int, str]] = []
    buffer: list[str] = []
    in_fence = False

    def flush(block_type: str = BLOCK_PARAGRAPH) -> None:
        nonlocal buffer
        text = "\n".join(buffer).strip()
        buffer = []
        if not text:
            return
        blocks.append(
            LayoutBlock(
                order_index=len(blocks),
                block_type=block_type,
                text=text,
                heading_path=_join_path(stack),
                depth=len(stack),
            )
        )

    index = 0
    while index < len(lines):
        line = lines[index]

        if _FENCE_RE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            index += 1
            continue
        if in_fence:
            buffer.append(line)
            index += 1
            continue

        if not line.strip():
            flush()
            index += 1
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            stack = _push_heading(stack, level, title)
            blocks.append(
                LayoutBlock(
                    order_index=len(blocks),
                    block_type=BLOCK_HEADING,
                    text=title,
                    heading_level=level,
                    heading_path=_join_path(stack),
                    depth=max(0, level - 1),
                )
            )
            index += 1
            continue

        if _is_table_start(lines, index):
            flush()
            end = _skip_table(lines, index)
            rows = lines[index:end]
            blocks.append(
                LayoutBlock(
                    order_index=len(blocks),
                    block_type=BLOCK_TABLE,
                    text="\n".join(rows).strip(),
                    heading_path=_join_path(stack),
                    depth=len(stack),
                    row_count=max(0, len(rows) - 2),
                    col_count=_markdown_table_columns(rows[0]),
                )
            )
            index = end
            continue

        if _IMAGE_ONLY_RE.match(line):
            flush()
            buffer.append(line.strip())
            flush(BLOCK_FIGURE)
            index += 1
            continue

        if _LIST_ITEM_RE.match(line):
            end = index
            while end < len(lines) and lines[end].strip() and not _HEADING_RE.match(lines[end]):
                if not _LIST_ITEM_RE.match(lines[end]) and end > index:
                    break
                end += 1
            flush()
            buffer.extend(lines[index:end])
            flush(BLOCK_LIST)
            index = end
            continue

        buffer.append(line)
        index += 1

    flush()
    return blocks


def _push_heading(stack: list[tuple[int, str]], level: int, title: str) -> list[tuple[int, str]]:
    trimmed = [entry for entry in stack if entry[0] < level]
    trimmed.append((level, title))
    return trimmed


def _join_path(stack: list[tuple[int, str]]) -> str | None:
    return " > ".join(title for _, title in stack) if stack else None


def _build_heading_tree(blocks: list[LayoutBlock]) -> list[dict[str, Any]]:
    roots: list[dict[str, Any]] = []
    open_nodes: list[tuple[int, dict[str, Any]]] = []

    for block in blocks:
        if block.block_type != BLOCK_HEADING:
            continue
        level = block.heading_level or 1
        node: dict[str, Any] = {
            "level": level,
            "title": block.text,
            "order_index": block.order_index,
            "page_number": block.page_number,
            "heading_path": block.heading_path,
            "children": [],
        }
        while open_nodes and open_nodes[-1][0] >= level:
            open_nodes.pop()
        if open_nodes:
            open_nodes[-1][1]["children"].append(node)
        else:
            roots.append(node)
        open_nodes.append((level, node))
    return roots


def _top_level_section_count(blocks: list[LayoutBlock]) -> int:
    levels = [b.heading_level for b in blocks if b.block_type == BLOCK_HEADING and b.heading_level]
    if not levels:
        return 0
    top = min(levels)
    return sum(1 for level in levels if level == top)


def _item_text(item: dict[str, Any], block_type: str) -> str:
    for key in ("md", "value", "text", "content"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if block_type == BLOCK_TABLE:
        return _rows_to_markdown(item.get("rows"))
    if block_type == BLOCK_FIGURE:
        caption = item.get("caption") or item.get("name")
        return str(caption).strip() if caption else ""
    return ""


def _rows_to_markdown(rows: Any) -> str:
    if not isinstance(rows, list) or not rows:
        return ""
    lines: list[str] = []
    for position, row in enumerate(rows):
        cells = row if isinstance(row, list) else [row]
        lines.append("| " + " | ".join(str(cell) for cell in cells) + " |")
        if position == 0:
            lines.append("| " + " | ".join("---" for _ in cells) + " |")
    return "\n".join(lines)


def _table_shape(item: dict[str, Any]) -> tuple[int | None, int | None]:
    rows = item.get("rows")
    if not isinstance(rows, list) or not rows:
        return None, None
    first = rows[0]
    col_count = len(first) if isinstance(first, list) else None
    return len(rows), col_count


def _markdown_table_columns(header: str) -> int:
    return len([cell for cell in header.strip().strip("|").split("|") if cell.strip()])


def _coerce_page_number(page: dict[str, Any]) -> int | None:
    for key in ("page_number", "page", "page_index"):
        value = page.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return None


def _coerce_level(item: dict[str, Any]) -> int:
    for key in ("lvl", "level", "heading_level"):
        value = item.get(key)
        if isinstance(value, int) and 1 <= value <= 6:
            return value
    return 1


def _coerce_bbox(item: dict[str, Any]) -> list[float] | None:
    raw = item.get("bBox") or item.get("bbox")
    if isinstance(raw, dict):
        keys = ("x", "y", "w", "h")
        if all(isinstance(raw.get(k), int | float) for k in keys):
            return [float(raw[k]) for k in keys]
        return None
    if isinstance(raw, list) and len(raw) >= 4:
        head = raw[:4]
        if all(isinstance(v, int | float) for v in head):
            return [float(v) for v in head]
    return None


# ---------------------------------------------------------------------------
# Persistence shapes
# ---------------------------------------------------------------------------


def build_layout_metadata(
    *,
    analysis: LayoutAnalysis,
    metrics: MarkdownMetrics,
    parser: str,
    tier: str | None = None,
    job_id: str | None = None,
    layout_artifact_key: str | None = None,
) -> dict[str, Any]:
    """Assemble ``document_versions.layout_metadata``.

    Block text is intentionally excluded: a 300-page document would bloat the
    JSONB column. Hierarchical Chunking reads the Markdown plus the MinIO layout
    artifact for text, and this column for structure.
    """
    return {
        "parser": parser,
        "parser_api_version": "v2",
        "tier": tier,
        "job_id": job_id,
        "source": analysis.source,
        "page_count": analysis.page_count,
        "section_count": analysis.section_count,
        "block_count": len(analysis.blocks),
        "metrics": metrics.as_dict(),
        "heading_tree": analysis.heading_tree,
        "blocks": [block.as_summary() for block in analysis.blocks],
        "tables": [
            block.as_summary() for block in analysis.blocks if block.block_type == BLOCK_TABLE
        ],
        "figures": [
            block.as_summary() for block in analysis.blocks if block.block_type == BLOCK_FIGURE
        ],
        "layout_artifact_key": layout_artifact_key,
    }


def build_layout_artifact(
    *,
    document_version_id: str,
    analysis: LayoutAnalysis,
    metrics: MarkdownMetrics,
    parser: str,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Full layout payload (with block text) stored beside the Markdown."""
    return {
        "document_version_id": document_version_id,
        "parser": parser,
        "job_id": job_id,
        "source": analysis.source,
        "page_count": analysis.page_count,
        "section_count": analysis.section_count,
        "metrics": metrics.as_dict(),
        "heading_tree": analysis.heading_tree,
        "blocks": [block.as_dict() for block in analysis.blocks],
    }


def build_ocr_segments(
    *,
    analysis: LayoutAnalysis,
    file_type: FileType,
) -> list[dict[str, Any]]:
    """Project layout blocks onto the interim OCR-segment shape.

    ``stage_chunking`` (v2 interim) consumes ``ocr_segments.json``; emitting it
    here keeps the pipeline green until Hierarchical Chunking reads
    ``layout_metadata`` directly. Drop this once that stage lands.

    Only paginated formats carry ``page_number``; DOCX/TXT get ``section_index``
    so citations never claim a page that does not exist.
    """
    paginated = file_type in PAGINATED_FILE_TYPES
    segments: list[dict[str, Any]] = []
    section: str | None = None
    section_index = 0

    for block in analysis.blocks:
        if block.block_type == BLOCK_HEADING:
            section = block.text
            section_index += 1
            continue
        if not block.text.strip():
            continue

        segment: dict[str, Any] = {
            "text": block.text,
            "page_number": block.page_number if paginated else None,
            "section": section,
            "order_index": len(segments),
            "block_type": block.block_type,
        }
        if not paginated and section_index:
            segment["section_index"] = section_index
        if block.heading_path:
            segment["heading_path"] = block.heading_path
        segments.append(segment)

    return segments


def resolve_page_count(*, analysis: LayoutAnalysis, file_type: FileType) -> int:
    """Value written to ``document_versions.page_count``.

    Physical pages for PDF/PPTX/XLSX; logical section count for DOCX/TXT, which
    matches how the local OCR parser reports it.
    """
    if file_type in PAGINATED_FILE_TYPES:
        return max(1, analysis.page_count)
    return max(1, analysis.section_count)
