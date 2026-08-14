# =============================================================================
# File: section_resolver.py
# Module/Service: Query Router — Section Extraction (FR11)
# Layer: Service
# Purpose: Deterministic heading match + parent/child resolution (0 LLM).
# Responsibilities:
#   - Rank heading candidates (exact → normalized → number → lexical)
#   - Resolve parent section and collect direct children in document order
# Dependencies:
#   - section_parser, section_patterns, RetrievalRepository
# Public Exports:
#   - ResolvedSection, ResolvedSectionItem, resolve_section_match,
#     collect_section_items
# Database/Table: document_chunks (heading_path, parent_chunk_id, layout_type)
# Related Modules: handlers.section_extraction_handler
# Important Notes:
#   - Never sort children by similarity — preserve chunk_index order.
#   - Heading match must not be treated as "no information".
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.ai.hierarchical_chunking.section_parser import (
    is_direct_child_number,
    normalize_heading_text,
    parse_numbered_heading,
)
from app.models.enums import ChunkLayoutType
from app.repositories.retrieval import ChunkHydrationRow
from app.services.query_router.section_patterns import (
    SectionIntent,
    SectionIntentMatch,
)


@dataclass(frozen=True, slots=True)
class ScoredHeading:
    """A heading candidate with a deterministic match score."""

    row: ChunkHydrationRow
    score: float
    match_type: str
    number: str | None
    title_normalized: str


@dataclass(frozen=True, slots=True)
class ResolvedSectionItem:
    """One subsection (or the section itself) in document order."""

    number: str | None
    title: str
    chunk_ids: list[UUID]
    page_numbers: list[int]
    content: str
    heading_path: str | None
    chunk_index: int | None
    document_id: UUID | None
    document_version_id: UUID | None = None
    workspace_id: UUID | None = None
    chunk_pages: list[int | None] = field(default_factory=list)
    chunk_snippets: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ResolvedSection:
    """Parent section plus ordered children / content items."""

    number: str | None
    title: str
    heading: ChunkHydrationRow
    items: list[ResolvedSectionItem]
    match_type: str
    intent: SectionIntent


def parse_heading_row(row: ChunkHydrationRow) -> tuple[str | None, str, str]:
    """Return ``(number, display_title, normalized_title)`` for a heading row."""
    raw = (row.section or row.content or "").strip()
    parsed = parse_numbered_heading(raw)
    display = parsed.title or parsed.raw or raw
    return parsed.number, display, normalize_heading_text(display)


def score_heading(
    row: ChunkHydrationRow,
    intent: SectionIntentMatch,
) -> ScoredHeading | None:
    """Score one heading against the extracted query intent.

    Priority: exact heading → normalized title → section number → token overlap.
    """
    number, _display, title_norm = parse_heading_row(row)
    content_norm = normalize_heading_text(row.content or "")
    section_norm = normalize_heading_text(row.section or "")
    path_norm = normalize_heading_text(row.heading_path or "")
    candidate = (intent.candidate_title or "").strip()
    query_norm = intent.normalized

    if candidate and candidate in {content_norm, section_norm, title_norm}:
        return ScoredHeading(
            row=row, score=1.0, match_type="exact_normalized",
            number=number, title_normalized=title_norm,
        )
    if query_norm and query_norm in {content_norm, section_norm, title_norm, path_norm}:
        return ScoredHeading(
            row=row, score=0.98, match_type="exact_query",
            number=number, title_normalized=title_norm,
        )
    if (
        intent.section_number
        and number == intent.section_number
        and (not candidate or _coverage(candidate, title_norm) >= 0.5)
    ):
        return ScoredHeading(
            row=row, score=0.95, match_type="section_number",
            number=number, title_normalized=title_norm,
        )
    if intent.section_number and number == intent.section_number:
        return ScoredHeading(
            row=row, score=0.88, match_type="section_number_only",
            number=number, title_normalized=title_norm,
        )
    if candidate and title_norm and (
        candidate in title_norm or title_norm in candidate
    ):
        coverage = _coverage(candidate, title_norm)
        return ScoredHeading(
            row=row, score=0.70 + 0.2 * coverage, match_type="normalized_contains",
            number=number, title_normalized=title_norm,
        )
    if candidate:
        coverage = _coverage(candidate, title_norm or content_norm)
        if coverage >= 0.7:
            return ScoredHeading(
                row=row, score=0.55 + 0.2 * coverage, match_type="token_overlap",
                number=number, title_normalized=title_norm,
            )
    return None


def resolve_section_match(
    intent: SectionIntentMatch,
    headings: list[ChunkHydrationRow],
) -> ScoredHeading | None:
    """Pick the best parent/leaf heading without vector similarity."""
    scored: list[ScoredHeading] = []
    for row in headings:
        hit = score_heading(row, intent)
        if hit is not None:
            scored.append(hit)
    if not scored:
        return None

    def _rank(item: ScoredHeading) -> tuple[float, int, int]:
        exact_number = (
            1
            if intent.section_number and item.number == intent.section_number
            else 0
        )
        # Prefer the parent when the query has no more-specific child number.
        depth = item.number.count(".") if item.number else 0
        prefer_shallow = 0 if intent.section_number and "." in intent.section_number else -depth
        return (item.score, exact_number, prefer_shallow)

    scored.sort(key=_rank, reverse=True)
    best = scored[0]
    if intent.section_number:
        exact = [s for s in scored if s.number == intent.section_number]
        if exact:
            exact.sort(
                key=lambda s: (s.score, -(s.row.chunk_index or 0)),
                reverse=True,
            )
            return exact[0]
    return best


def collect_direct_heading_children(
    parent: ChunkHydrationRow,
    headings: list[ChunkHydrationRow],
) -> list[ChunkHydrationRow]:
    """Direct child headings in document order (never similarity-sorted)."""
    parent_number, _, _ = parse_heading_row(parent)
    parent_id = parent.chunk_id
    children: list[ChunkHydrationRow] = []
    for row in headings:
        if row.document_version_id != parent.document_version_id:
            continue
        if parent_id is not None and row.parent_chunk_id == parent_id:
            if row.layout_type in {None, ChunkLayoutType.heading}:
                children.append(row)
            continue
        child_number, _, _ = parse_heading_row(row)
        if (
            parent_number
            and child_number
            and is_direct_child_number(parent_number, child_number)
        ):
            children.append(row)

    seen: set[UUID] = set()
    ordered: list[ChunkHydrationRow] = []
    for row in sorted(children, key=lambda r: r.chunk_index or 0):
        if row.chunk_id in seen:
            continue
        seen.add(row.chunk_id)
        ordered.append(row)
    return ordered


def next_heading_index(
    heading: ChunkHydrationRow,
    headings: list[ChunkHydrationRow],
) -> int | None:
    """Chunk index of the next heading at the same or shallower depth."""
    start = heading.chunk_index
    if start is None:
        return None
    heading_depth = heading.depth if heading.depth is not None else 0
    later = [
        row
        for row in headings
        if row.document_version_id == heading.document_version_id
        and row.chunk_index is not None
        and row.chunk_index > start
        and (row.depth is None or row.depth <= heading_depth)
        and row.chunk_id != heading.chunk_id
    ]
    if not later:
        return None
    later.sort(key=lambda r: r.chunk_index or 0)
    return later[0].chunk_index


def item_from_heading(
    heading: ChunkHydrationRow,
    content_chunks: list[ChunkHydrationRow],
) -> ResolvedSectionItem:
    """Build one output item from a heading plus its extractive content."""
    number, title, _ = parse_heading_row(heading)
    texts: list[str] = []
    chunk_ids: list[UUID] = []
    chunk_pages: list[int | None] = []
    chunk_snippets: list[str] = []
    pages: list[int] = []
    seen_bodies: set[str] = set()

    def _add_chunk(row: ChunkHydrationRow, *, as_body: bool) -> None:
        if row.chunk_id in chunk_ids:
            return
        body = (row.content or "").strip()
        chunk_ids.append(row.chunk_id)
        chunk_pages.append(row.page_number)
        chunk_snippets.append((body or title)[:240])
        if row.page_number is not None and row.page_number not in pages:
            pages.append(row.page_number)
        if as_body and body:
            fingerprint = " ".join(body.casefold().split())
            if fingerprint in seen_bodies:
                return
            seen_bodies.add(fingerprint)
            texts.append(body)

    _add_chunk(heading, as_body=False)
    for chunk in content_chunks:
        if chunk.layout_type == ChunkLayoutType.heading:
            continue
        _add_chunk(chunk, as_body=True)
    return ResolvedSectionItem(
        number=number,
        title=title,
        chunk_ids=chunk_ids,
        page_numbers=pages,
        content="\n".join(texts).strip(),
        heading_path=heading.heading_path,
        chunk_index=heading.chunk_index,
        document_id=heading.document_id,
        document_version_id=heading.document_version_id,
        workspace_id=heading.workspace_id,
        chunk_pages=chunk_pages,
        chunk_snippets=chunk_snippets,
    )


def _coverage(query: str, heading: str) -> float:
    q_tokens = [t for t in query.split() if len(t) > 1]
    h_tokens = [t for t in heading.split() if len(t) > 1]
    if not q_tokens or not h_tokens:
        return 0.0
    q_set, h_set = set(q_tokens), set(h_tokens)
    overlap = len(q_set & h_set)
    return overlap / max(1, min(len(q_set), len(h_set)))
