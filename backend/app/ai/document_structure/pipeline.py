# =============================================================================
# File: pipeline.py
# Module/Service: Document Structure Extraction (FR8 / TASK-CMP-01)
# Layer: Service
# Purpose: Pure (no I/O, no LLM) extraction of a normalized structure tree
#   from the FULL ingested document corpus.
# Responsibilities:
#   - Flatten all chunks into document-order lines
#   - Detect markers (parser headings → numbering → OCR-tolerant keywords)
#   - Build parent/child hierarchy and bind page/chunk evidence
# Public Exports:
#   - extract_structure, extract_from_text, extract_from_pages,
#     added_canonical_keys
# Database/Table: N/A (operates on DocumentCorpus assembled by the service)
# Related Modules: DocumentStructureExtractor, hierarchical_chunking.section_parser
# Important Notes:
#   - Never uses retrieval / top-k / embeddings / LLM.
#   - Original line text is preserved; only type+number are normalized.
#   - Empty / malformed input returns a DOCUMENT with zero sections (no crash).
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

from app.ai.document_structure.patterns import (
    classify_heading_line,
    is_boilerplate_line,
    strip_markdown_heading,
)
from app.ai.document_structure.types import (
    COMPATIBLE_CHILDREN,
    CONFIDENCE_SCORE,
    TYPE_LEVEL,
    CorpusChunk,
    CorpusLine,
    DetectedMarker,
    DocumentCorpus,
    DocumentStructure,
    ExtractionConfidence,
    SourceSpan,
    StructuralUnit,
    StructuralUnitType,
)
from app.ai.hierarchical_chunking.constants import FENCE_RE
from app.ai.hierarchical_chunking.section_parser import heading_number_parent

_HEADING_LAYOUT = "heading"


def extract_structure(corpus: DocumentCorpus) -> DocumentStructure:
    """Build a normalized structure tree from the full ingested corpus."""
    chunks = sorted(corpus.chunks, key=lambda c: c.chunk_index)
    lines = flatten_chunks(chunks)
    heading_titles = _heading_titles_from_layout(corpus.layout_metadata)
    markers = detect_markers(lines, known_heading_titles=heading_titles)
    root, stats = build_tree(
        document_id=corpus.document_id,
        title=corpus.title or "",
        lines=lines,
        markers=markers,
    )
    pages = {line.page_number for line in lines if line.page_number is not None}
    stats["pages_processed"] = len(pages) or (corpus.page_count or 0)
    stats["chunks_processed"] = len(chunks)
    stats["lines_processed"] = len(lines)
    stats["structural_units_detected"] = max(0, stats["structural_units_detected"])
    return DocumentStructure(
        document_id=corpus.document_id,
        title=corpus.title or "",
        metadata=stats,
        sections=list(root.children),
        version_id=corpus.version_id,
        workspace_id=corpus.workspace_id,
        root=root,
    )


def extract_from_text(
    text: str,
    *,
    document_id: UUID | None = None,
    title: str = "",
    page_number: int | None = 1,
) -> DocumentStructure:
    """Convenience wrapper: one synthetic chunk covering the whole text."""
    doc_id = document_id or uuid4()
    chunk = CorpusChunk(
        chunk_id=uuid4(),
        chunk_index=0,
        content=text or "",
        page_number=page_number,
        layout_type=None,
    )
    return extract_structure(
        DocumentCorpus(document_id=doc_id, title=title, chunks=[chunk])
    )


def extract_from_pages(
    pages: Sequence[tuple[int, str]],
    *,
    document_id: UUID | None = None,
    title: str = "",
) -> DocumentStructure:
    """One chunk per page — used for multi-page binding and PDF regression tests."""
    doc_id = document_id or uuid4()
    chunks = [
        CorpusChunk(
            chunk_id=uuid4(),
            chunk_index=index,
            content=body or "",
            page_number=page_number,
        )
        for index, (page_number, body) in enumerate(pages)
    ]
    return extract_structure(
        DocumentCorpus(
            document_id=doc_id,
            title=title,
            chunks=chunks,
            page_count=len(pages),
        )
    )


def added_canonical_keys(
    baseline: DocumentStructure,
    candidate: DocumentStructure,
) -> set[str]:
    """Keys present in ``candidate`` but not ``baseline``.

    This is the structure-level check that prevents the false positive
    "V2 added Điều 1.2/1.3" when retrieval simply missed V1 chunks.
    """
    return candidate.canonical_keys() - baseline.canonical_keys()


def flatten_chunks(chunks: Sequence[CorpusChunk]) -> list[CorpusLine]:
    """Split every chunk into original lines; chunks are joined as line breaks."""
    lines: list[CorpusLine] = []
    for chunk in chunks:
        content = (chunk.content or "").replace("\r\n", "\n").replace("\r", "\n")
        raw_lines = content.split("\n") if content else [""]
        is_heading = (chunk.layout_type or "").lower() == _HEADING_LAYOUT
        for line_no, raw in enumerate(raw_lines):
            boilerplate = is_boilerplate_line(raw)
            lines.append(
                CorpusLine(
                    text=raw,
                    chunk_id=chunk.chunk_id,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    line_in_chunk=line_no,
                    is_heading_chunk=is_heading and line_no == 0,
                    skip_as_boilerplate=boilerplate,
                )
            )
    return lines


def detect_markers(
    lines: Sequence[CorpusLine],
    *,
    known_heading_titles: set[str] | None = None,
) -> list[DetectedMarker]:
    """Single pass over the full corpus. Does not query retrieval."""
    known = known_heading_titles or set()
    markers: list[DetectedMarker] = []
    in_fence = False
    in_article = False

    for index, line in enumerate(lines):
        stripped = (line.text or "").strip()
        if FENCE_RE.match(stripped):
            in_fence = not in_fence
            continue
        if in_fence or line.skip_as_boilerplate or not stripped:
            continue
        if stripped.startswith("|"):
            continue

        body, _level = strip_markdown_heading(stripped)
        known_heading = line.is_heading_chunk or _normalize_title_key(body) in known
        marker = classify_heading_line(
            line.text,
            line_index=index,
            in_article=in_article,
            known_heading=known_heading,
        )
        if marker is None:
            continue
        marker = _maybe_consume_next_line_title(marker, lines, index)
        markers.append(marker)
        if marker.unit_type is StructuralUnitType.ARTICLE:
            in_article = True
        elif marker.unit_type in {
            StructuralUnitType.CHAPTER,
            StructuralUnitType.APPENDIX,
        }:
            in_article = False

    return markers


def build_tree(
    *,
    document_id: UUID,
    title: str,
    lines: Sequence[CorpusLine],
    markers: Sequence[DetectedMarker],
) -> tuple[StructuralUnit, dict[str, Any]]:
    """Attach markers into a parent/child tree and bind exclusive text spans."""
    used_ids: set[str] = set()
    root = StructuralUnit(
        id=_make_id(StructuralUnitType.DOCUMENT, None, 0, used_ids),
        document_id=document_id,
        type=StructuralUnitType.DOCUMENT,
        number=None,
        title=title,
        text="",
        level=0,
        parent_id=None,
        order_index=0,
    )
    if not markers:
        root.text = _join_lines(lines, 0, len(lines))
        _bind_source(root, lines, 0, len(lines))
        return root, _empty_stats()

    stack: list[StructuralUnit] = [root]
    units_in_order: list[tuple[StructuralUnit, int]] = []

    for order, marker in enumerate(markers, start=1):
        unit = StructuralUnit(
            id=_make_id(marker.unit_type, marker.number, order, used_ids),
            document_id=document_id,
            type=marker.unit_type,
            number=marker.number,
            title=marker.title,
            text="",
            level=0,
            parent_id=None,
            order_index=order,
            confidence=CONFIDENCE_SCORE[marker.confidence],
            confidence_label=marker.confidence,
            original_heading=marker.raw_line,
            detection_source=marker.source,
        )
        parent = _find_parent(stack, marker)
        while len(stack) > 1 and stack[-1] is not parent:
            stack.pop()
        unit.parent_id = parent.id
        unit.level = parent.level + 1
        parent.children.append(unit)
        stack.append(unit)
        units_in_order.append((unit, marker.line_index))

    # Exclusive text: each unit owns [own_marker, next_marker).
    starts = [start for _, start in units_in_order]
    for index, (unit, start) in enumerate(units_in_order):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        unit.text = _join_lines(lines, start, end)
        _bind_source(unit, lines, start, end)

    first_start = starts[0]
    root.text = _join_lines(lines, 0, first_start)
    _bind_source(root, lines, 0, first_start)

    stats = _collect_stats(root)
    return root, stats


def _find_parent(stack: Sequence[StructuralUnit], marker: DetectedMarker) -> StructuralUnit:
    wanted = heading_number_parent(marker.number)
    child_type = marker.unit_type
    child_level = TYPE_LEVEL[child_type]
    fallback: StructuralUnit | None = None

    for candidate in reversed(stack):
        allowed = COMPATIBLE_CHILDREN.get(candidate.type, frozenset())
        if child_type not in allowed:
            continue
        if TYPE_LEVEL[candidate.type] >= child_level:
            continue
        if wanted:
            if candidate.number == wanted:
                return candidate
            if fallback is None:
                fallback = candidate
            continue
        return candidate
    return fallback or stack[0]


def _maybe_consume_next_line_title(
    marker: DetectedMarker,
    lines: Sequence[CorpusLine],
    index: int,
) -> DetectedMarker:
    """Two-line form: ``ĐIỀU 1`` / ``PHẠM VI CÔNG VIỆC``."""
    if marker.title.strip():
        return marker
    if marker.unit_type not in {
        StructuralUnitType.ARTICLE,
        StructuralUnitType.CHAPTER,
        StructuralUnitType.APPENDIX,
        StructuralUnitType.SECTION,
    }:
        return marker
    for peek in range(index + 1, min(index + 4, len(lines))):
        candidate = lines[peek]
        body = (candidate.text or "").strip()
        if not body or candidate.skip_as_boilerplate:
            continue
        if classify_heading_line(candidate.text, line_index=peek) is not None:
            return marker
        if len(body) > 120:
            return marker
        return DetectedMarker(
            unit_type=marker.unit_type,
            number=marker.number,
            title=body.strip("-—– ").strip(),
            raw_line=marker.raw_line,
            confidence=marker.confidence,
            source=marker.source,
            line_index=marker.line_index,
        )
    return marker


def _bind_source(
    unit: StructuralUnit,
    lines: Sequence[CorpusLine],
    start: int,
    end: int,
) -> None:
    chunk_ids: list[UUID] = []
    seen: set[UUID] = set()
    pages: list[int] = []
    spans: list[SourceSpan] = []
    span_seen: set[tuple[UUID | None, int | None]] = set()

    for line in lines[start:end]:
        if line.skip_as_boilerplate:
            continue
        if line.chunk_id is not None and line.chunk_id not in seen:
            seen.add(line.chunk_id)
            chunk_ids.append(line.chunk_id)
        if line.page_number is not None and line.page_number not in pages:
            pages.append(line.page_number)
        key = (line.chunk_id, line.page_number)
        if key not in span_seen and (line.chunk_id is not None or line.page_number is not None):
            span_seen.add(key)
            spans.append(
                SourceSpan(chunk_id=line.chunk_id, page_number=line.page_number)
            )

    unit.chunk_ids = chunk_ids
    unit.source_spans = spans
    if pages:
        unit.page_start = min(pages)
        unit.page_end = max(pages)


def _join_lines(lines: Sequence[CorpusLine], start: int, end: int) -> str:
    parts: list[str] = []
    for line in lines[start:end]:
        if line.skip_as_boilerplate:
            continue
        parts.append(line.text)
    return "\n".join(parts).strip("\n")


def _make_id(
    unit_type: StructuralUnitType,
    number: str | None,
    order_index: int,
    used: set[str],
) -> str:
    slug = unit_type.value.lower().replace("_", "-")
    if number:
        base = f"{slug}-{number.replace('.', '-')}"
    else:
        base = f"{slug}-{order_index}"
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}-{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _heading_titles_from_layout(layout_metadata: dict[str, Any] | None) -> set[str]:
    if not layout_metadata:
        return set()
    titles: set[str] = set()

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            title = str(node.get("title") or "").strip()
            if title:
                titles.add(_normalize_title_key(title))
            walk(node.get("children"))

    walk(layout_metadata.get("heading_tree"))
    return titles


def _normalize_title_key(text: str) -> str:
    body, _ = strip_markdown_heading(text)
    return " ".join(body.casefold().split())


def _empty_stats() -> dict[str, Any]:
    return {
        "pages_processed": 0,
        "chunks_processed": 0,
        "lines_processed": 0,
        "structural_units_detected": 0,
        "articles_detected": 0,
        "clauses_detected": 0,
        "appendices_detected": 0,
        "low_confidence_units": 0,
        "detection_llm_calls": 0,
    }


def _collect_stats(root: StructuralUnit) -> dict[str, Any]:
    articles = clauses = appendices = low = units = 0
    for unit in root.walk():
        if unit.type is StructuralUnitType.DOCUMENT:
            continue
        units += 1
        if unit.type is StructuralUnitType.ARTICLE:
            articles += 1
        elif unit.type in {StructuralUnitType.CLAUSE, StructuralUnitType.SUB_CLAUSE}:
            clauses += 1
        elif unit.type is StructuralUnitType.APPENDIX:
            appendices += 1
        if unit.confidence_label is ExtractionConfidence.LOW:
            low += 1
    return {
        "pages_processed": 0,
        "chunks_processed": 0,
        "lines_processed": 0,
        "structural_units_detected": units,
        "articles_detected": articles,
        "clauses_detected": clauses,
        "appendices_detected": appendices,
        "low_confidence_units": low,
        "detection_llm_calls": 0,
    }
