# =============================================================================
# File: section_extraction_handler.py
# Module/Service: Query Router — Section Extraction Handler (FR11)
# Layer: Service
# Purpose: Structure-aware section listing from heading metadata (0 LLM).
# Responsibilities:
#   - Detect section intent; match headings; collect children in document order
#   - Render extractive answers with per-item citations
#   - Downgrade to complex only when no heading can be resolved
# Dependencies:
#   - RetrievalRepository, section_patterns, section_resolver
# Public Exports:
#   - SectionExtractionHandler
# Database/Table: document_chunks
# Related Modules: section_branch, QueryOrchestrator
# Important Notes:
#   - 0 LLM calls. Never conclude "no information" after a heading match.
#   - Children stay in chunk_index order (not similarity).
# =============================================================================

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.models.enums import RouteType
from app.repositories.retrieval import ChunkHydrationRow, RetrievalRepository
from app.services.query_router.response_models import QueryRouterResult
from app.services.query_router.schemas import CitationRef
from app.services.query_router.section_patterns import (
    SectionIntent,
    SectionIntentMatch,
    detect_section_intent,
)
from app.services.query_router.section_resolver import (
    ResolvedSection,
    ResolvedSectionItem,
    ScoredHeading,
    collect_direct_heading_children,
    item_from_heading,
    next_heading_index,
    parse_heading_row,
    resolve_section_match,
)

logger = get_logger(__name__)

COMPLEX_STATUS = "pending_llm_pipeline"
_MAX_ITEM_CONTENT_CHARS = 800


class SectionExtractionHandler:
    """Deterministic section extraction — headings + children, 0 LLM."""

    def __init__(self, *, retrieval_repo: RetrievalRepository) -> None:
        self._repo = retrieval_repo

    async def handle(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        intent: SectionIntentMatch | None = None,
    ) -> QueryRouterResult:
        """Extract a structured section answer or downgrade to complex.

        Args:
            workspace_id: Tenant scope.
            query_text: Raw user question.
            intent: Optional precomputed classifier match.
        """
        match = intent if intent is not None else detect_section_intent(query_text)
        headings = await self._repo.search_heading_chunks(
            workspace_id,
            section_number=match.section_number,
            title_query=match.candidate_title,
        )
        if not headings and (match.section_number or match.candidate_title):
            headings = await self._repo.search_heading_chunks(workspace_id)

        scored = resolve_section_match(match, headings)
        if scored is None:
            if match.intent is SectionIntent.outline:
                scored_outline = await self._try_outline(workspace_id, headings)
                if scored_outline is not None:
                    return await self._build_success(
                        workspace_id, match, scored_outline.row, headings,
                        match_type=scored_outline.match_type,
                    )
            logger.info(
                "section_extraction_no_heading",
                workspace_id=str(workspace_id),
                rule=match.rule_name,
            )
            return self._downgrade("no_heading_match")

        return await self._build_success(
            workspace_id, match, scored.row, headings, match_type=scored.match_type
        )

    async def _try_outline(
        self,
        workspace_id: UUID,
        headings: list[ChunkHydrationRow],
    ) -> ScoredHeading | None:
        if not headings:
            headings = await self._repo.search_heading_chunks(workspace_id)
        if not headings:
            return None
        headings_sorted = sorted(
            headings,
            key=lambda r: (r.depth if r.depth is not None else 0, r.chunk_index or 0),
        )
        root = headings_sorted[0]
        number, _, title_norm = parse_heading_row(root)
        return ScoredHeading(
            row=root,
            score=0.4,
            match_type="outline_fallback",
            number=number,
            title_normalized=title_norm,
        )

    async def _build_success(
        self,
        workspace_id: UUID,
        match: SectionIntentMatch,
        heading: ChunkHydrationRow,
        headings: list[ChunkHydrationRow],
        *,
        match_type: str = "heading",
    ) -> QueryRouterResult:
        version_headings = [
            row
            for row in headings
            if row.document_version_id == heading.document_version_id
        ]
        if len(version_headings) < 2:
            version_headings = await self._repo.list_version_heading_chunks(
                workspace_id, heading.document_version_id
            )

        children = collect_direct_heading_children(heading, version_headings)
        if not children:
            children = await self._repo.list_child_chunks(
                workspace_id, heading.chunk_id, headings_only=True
            )

        intent = match.intent or SectionIntent.list_children
        if intent is SectionIntent.section_content or (
            intent is SectionIntent.list_children and not children
        ):
            items = [
                await self._item_with_content(
                    workspace_id, heading, version_headings
                )
            ]
        else:
            items = []
            for child in children:
                items.append(
                    await self._item_with_content(
                        workspace_id, child, version_headings
                    )
                )
            if not items:
                items = [
                    await self._item_with_content(
                        workspace_id, heading, version_headings
                    )
                ]

        number, title, _ = parse_heading_row(heading)
        resolved = ResolvedSection(
            number=number,
            title=title,
            heading=heading,
            items=items,
            match_type=match_type,
            intent=intent,
        )
        answer = render_section_answer(query_text=match.original, resolved=resolved)
        citations = citations_from_items(items)
        payload = section_payload(resolved)
        logger.info(
            "section_extraction_ok",
            workspace_id=str(workspace_id),
            section_number=number,
            item_count=len(items),
            match_type=match_type,
            llm_calls=0,
        )
        return QueryRouterResult(
            route_type=RouteType.section_extraction,
            answer=answer,
            citation_refs=citations,
            confidence=1.0,
            verify=True,
            status=None,
            metadata={
                "route_type": RouteType.section_extraction.value,
                "answer_type": "extractive",
                "match_type": match_type,
                "llm_calls_count": 0,
                "section": payload["section"],
                "items": payload["items"],
            },
        )

    async def _item_with_content(
        self,
        workspace_id: UUID,
        heading: ChunkHydrationRow,
        headings: list[ChunkHydrationRow],
    ) -> ResolvedSectionItem:
        content_chunks = await self._collect_content(
            workspace_id, heading, headings
        )
        return item_from_heading(heading, content_chunks)

    async def _collect_content(
        self,
        workspace_id: UUID,
        heading: ChunkHydrationRow,
        headings: list[ChunkHydrationRow],
    ) -> list[ChunkHydrationRow]:
        """Gather subsection body: children → heading_path → neighbor span."""
        collected: list[ChunkHydrationRow] = []
        seen: set[UUID] = set()

        def _add(rows: list[ChunkHydrationRow]) -> None:
            for row in rows:
                if row.chunk_id in seen:
                    continue
                seen.add(row.chunk_id)
                collected.append(row)

        children = await self._repo.list_child_chunks(workspace_id, heading.chunk_id)
        _add(children)

        if heading.heading_path:
            prefixed = await self._repo.list_chunks_by_heading_path_prefix(
                workspace_id,
                heading.document_version_id,
                heading.heading_path,
            )
            _add(prefixed)

        start = (heading.chunk_index or 0) + 1
        end = next_heading_index(heading, headings)
        span = await self._repo.list_chunks_in_index_range(
            workspace_id,
            heading.document_version_id,
            start_index=start,
            end_index=end,
        )
        _add(span)

        if not collected and heading.chunk_index is not None:
            neighbors = await self._repo.fetch_sibling_chunks(
                workspace_id,
                [(heading.document_version_id, heading.chunk_index)],
                window=3,
                exclude_chunk_ids={heading.chunk_id},
            )
            _add(neighbors)

        collected.sort(key=lambda r: r.chunk_index or 0)
        return collected

    def _downgrade(self, reason: str) -> QueryRouterResult:
        return QueryRouterResult(
            route_type=RouteType.complex,
            answer=None,
            citation_refs=[],
            confidence=None,
            verify=False,
            status=COMPLEX_STATUS,
            metadata={"fallback_reason": reason},
        )


def section_payload(resolved: ResolvedSection) -> dict[str, Any]:
    """Internal contract for ``section_extraction`` metadata."""
    return {
        "section": {
            "number": resolved.number,
            "title": resolved.title,
        },
        "items": [
            {
                "number": item.number,
                "title": item.title,
                "chunk_ids": [str(cid) for cid in item.chunk_ids],
                "page_numbers": item.page_numbers,
                "document_id": str(item.document_id) if item.document_id else None,
                "document_version_id": (
                    str(item.document_version_id) if item.document_version_id else None
                ),
                "citations": [
                    {
                        "chunk_id": str(cid),
                        "document_id": str(item.document_id) if item.document_id else None,
                        "document_version_id": (
                            str(item.document_version_id)
                            if item.document_version_id
                            else None
                        ),
                        "page_number": (
                            item.chunk_pages[index]
                            if index < len(item.chunk_pages)
                            else None
                        ),
                    }
                    for index, cid in enumerate(item.chunk_ids)
                ],
            }
            for item in resolved.items
        ],
    }


def citations_from_items(items: list[ResolvedSectionItem]) -> list[CitationRef]:
    """One citation per source chunk — provenance survives body dedupe."""
    refs: list[CitationRef] = []
    seen: set[UUID] = set()
    for item in items:
        for index, chunk_id in enumerate(item.chunk_ids):
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            snippet = ""
            if index < len(item.chunk_snippets):
                snippet = (item.chunk_snippets[index] or "").strip()
            if not snippet:
                snippet = (
                    item.content.split("\n", 1)[0][:240]
                    if item.content
                    else item.title
                )
            page: int | None = None
            if index < len(item.chunk_pages):
                page = item.chunk_pages[index]
            elif index < len(item.page_numbers):
                page = item.page_numbers[index]
            refs.append(
                CitationRef(
                    chunk_id=chunk_id,
                    document_id=item.document_id,
                    page_number=page,
                    verify=True,
                    text_snippet=(snippet or item.title or "")[:240] or None,
                    document_version_id=item.document_version_id,
                    workspace_id=item.workspace_id,
                )
            )
    return refs


def render_section_answer(*, query_text: str, resolved: ResolvedSection) -> str:
    """Render a structured extractive answer (no paraphrase / no LLM).

    Presentation only: do not emit markdown ordered lists such as ``1. 4.1 Title``.
    Section numbers are document identifiers and must stay intact for the UI adapter.
    """
    heading_label = _format_heading(resolved.number, resolved.title)
    _ = query_text
    items = _dedupe_items_for_display(resolved.items)
    if not items:
        return f"{heading_label}."

    lines: list[str] = []
    if resolved.intent is SectionIntent.section_content and len(items) == 1:
        item = items[0]
        lines.append(_format_heading(item.number, item.title))
        lines.extend(_body_lines(item.content, number=item.number, title=item.title))
        return "\n".join(lines).strip()

    lines.append(heading_label)
    lines.append("")
    for index, item in enumerate(items):
        lines.append(_format_heading(item.number, item.title))
        lines.extend(_body_lines(item.content, number=item.number, title=item.title))
        if index < len(items) - 1:
            lines.append("")
    return "\n".join(lines).strip()


def _dedupe_items_for_display(items: list[ResolvedSectionItem]) -> list[ResolvedSectionItem]:
    """Merge display items that share the same section number (presentation only)."""
    grouped: dict[str, ResolvedSectionItem] = {}
    order: list[str] = []
    for item in items:
        key = item.number or item.title or str(len(order))
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = item
            order.append(key)
            continue
        chunk_ids = list(existing.chunk_ids)
        chunk_pages = list(existing.chunk_pages)
        chunk_snippets = list(existing.chunk_snippets)
        for index, cid in enumerate(item.chunk_ids):
            if cid in chunk_ids:
                continue
            chunk_ids.append(cid)
            chunk_pages.append(
                item.chunk_pages[index] if index < len(item.chunk_pages) else None
            )
            chunk_snippets.append(
                item.chunk_snippets[index] if index < len(item.chunk_snippets) else ""
            )
        pages = list(existing.page_numbers)
        for page in item.page_numbers:
            if page not in pages:
                pages.append(page)
        grouped[key] = ResolvedSectionItem(
            number=existing.number or item.number,
            title=existing.title or item.title,
            chunk_ids=chunk_ids,
            page_numbers=pages,
            content=_merge_unique_paragraphs(existing.content, item.content),
            heading_path=existing.heading_path,
            chunk_index=existing.chunk_index,
            document_id=existing.document_id,
            document_version_id=existing.document_version_id or item.document_version_id,
            workspace_id=existing.workspace_id or item.workspace_id,
            chunk_pages=chunk_pages,
            chunk_snippets=chunk_snippets,
        )
    return [grouped[key] for key in order]


def _format_heading(number: str | None, title: str) -> str:
    title = (title or "").strip()
    number = (number or "").strip()
    if number and title:
        if "." in number:
            return f"{number} {title}"
        return f"{number}. {title}"
    if number:
        return number
    return title


def _normalize_display_text(text: str) -> str:
    return " ".join((text or "").casefold().split())


def _unescape_html_entities(text: str) -> str:
    return (
        (text or "")
        .replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&amp;", "&")
    )


def _is_html_artifact_only(line: str) -> bool:
    compact = "".join(_unescape_html_entities(line).split())
    if not compact:
        return True
    stripped = re.sub(r"</?(?:tr|td|th|table|thead|tbody|tfoot)(?:\s[^>]*)?>", "", compact, flags=re.I)
    return stripped == "" and bool(re.search(r"</?(?:tr|td|th|table)\b", compact, re.I))


def _body_lines(content: str, *, number: str | None, title: str) -> list[str]:
    if not content:
        return []
    clipped = _unescape_html_entities(content.strip())
    if len(clipped) > _MAX_ITEM_CONTENT_CHARS:
        clipped = clipped[:_MAX_ITEM_CONTENT_CHARS].rsplit(" ", 1)[0] + "…"

    heading_keys = {
        _normalize_display_text(title),
        _normalize_display_text(_format_heading(number, title)),
    }
    if number and title:
        heading_keys.add(_normalize_display_text(f"{number} {title}"))
        heading_keys.add(_normalize_display_text(f"{number}. {title}"))

    lines: list[str] = []
    seen_lines: set[str] = set()
    for raw_line in clipped.splitlines():
        line = raw_line.strip().lstrip("-*• \t")
        if not line or _is_html_artifact_only(line):
            continue
        fingerprint = _normalize_display_text(line)
        if fingerprint in heading_keys or fingerprint in seen_lines:
            continue
        seen_lines.add(fingerprint)
        lines.append(line)
    return lines


def _merge_unique_paragraphs(*parts: str) -> str:
    """Join item bodies without dropping provenance of duplicate chunks."""
    seen: set[str] = set()
    lines: list[str] = []
    for part in parts:
        for raw in (part or "").splitlines():
            line = raw.strip()
            fingerprint = _normalize_display_text(line)
            if not fingerprint or fingerprint in seen:
                continue
            seen.add(fingerprint)
            lines.append(line)
    return "\n".join(lines)
