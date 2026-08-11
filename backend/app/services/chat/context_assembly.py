# =============================================================================
# File: context_assembly.py
# Module/Service: Chat Service / Prompt Construction (FR4) — Context Assembly
# Layer: Service
# Purpose: Turn reranked retrieval candidates into coherent, grounded LLM
#   context — bounded neighbor expansion, dedup, section grouping, ordering —
#   BEFORE Prompt Construction (RAG answer-quality P1, spec §4-§6, §16-§18).
# Responsibilities:
#   - Deduplicate near-identical chunks
#   - Bounded neighbor (sibling) expansion via ChunkContextPort (0 LLM)
#   - Deterministic representative-coverage expansion for document-level
#     questions when section diversity is too low (0 LLM)
#   - Group chunks by (document, section) and order groups (lost-in-middle
#     mitigation for global questions; strongest-first for focused questions)
#   - Compute retrieval_quality_debug diagnostics (candidate/rerank/coverage
#     counts, token budget, deterministic coverage_score)
# Dependencies:
#   - app.services.retrieval.schemas.RetrievalCandidate
#   - app.services.retrieval.query_expansion (query intent classification)
#   - app.ai.tokens.count_tokens
# Public Exports:
#   - ChunkContextPort, RetrievalRepositoryContextPort, ContextAssemblyConfig,
#     RetrievalQualityDebug, ContextAssemblyResult, assemble_context
# Database/Table: N/A (DB access only via injected ChunkContextPort)
# Related Modules: answer_generator.PromptAnswerGenerator, prompt_builder,
#   app.repositories.retrieval.RetrievalRepository
# Important Notes:
#   - 0 LLM, 0 embedding. Never blindly includes a whole document — every
#     expansion is bounded by config (window / max_total / limit).
#   - Originals (already-reranked candidates) always win over expansions when
#     trimming to the context budget — expansions only fill gaps.
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from app.ai.tokens import count_tokens
from app.core.logging import get_logger
from app.services.retrieval.query_expansion import QueryIntent, classify_query_intent
from app.services.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


class ChunkContextPort(Protocol):
    """Bounded, deterministic chunk lookups needed for context assembly.

    Production implementation (``RetrievalRepositoryContextPort``) wraps
    ``RetrievalRepository`` (Postgres). Tests inject a fake — assembly logic
    never touches a DB session directly (Service layer stays DB-agnostic).
    """

    async def fetch_siblings(
        self,
        workspace_id: UUID,
        seeds: list[tuple[UUID, int]],
        *,
        window: int,
        exclude_chunk_ids: set[UUID],
        max_total: int,
    ) -> list[RetrievalCandidate]: ...

    async def fetch_representative(
        self,
        workspace_id: UUID,
        document_version_id: UUID,
        *,
        limit: int,
    ) -> list[RetrievalCandidate]: ...


class RetrievalRepositoryContextPort:
    """Production ``ChunkContextPort`` backed by ``RetrievalRepository``."""

    def __init__(self, repo: Any) -> None:
        self._repo = repo

    async def fetch_siblings(
        self,
        workspace_id: UUID,
        seeds: list[tuple[UUID, int]],
        *,
        window: int,
        exclude_chunk_ids: set[UUID],
        max_total: int,
    ) -> list[RetrievalCandidate]:
        rows = await self._repo.fetch_sibling_chunks(
            workspace_id,
            seeds,
            window=window,
            exclude_chunk_ids=exclude_chunk_ids,
            max_total=max_total,
        )
        return [_row_to_candidate(workspace_id, row, method="context_expansion") for row in rows]

    async def fetch_representative(
        self,
        workspace_id: UUID,
        document_version_id: UUID,
        *,
        limit: int,
    ) -> list[RetrievalCandidate]:
        rows = await self._repo.fetch_representative_chunks(
            workspace_id, document_version_id, limit=limit
        )
        return [_row_to_candidate(workspace_id, row, method="coverage") for row in rows]


def _row_to_candidate(workspace_id: UUID, row: Any, *, method: str) -> RetrievalCandidate:
    return RetrievalCandidate(
        workspace_id=workspace_id,
        text_snippet=row.content or "",
        retrieval_method=method,
        raw_score=0.0,
        document_id=row.document_id,
        chunk_id=row.chunk_id,
        score=None,
        source_methods=[method],
        page_number=row.page_number,
        section_index=row.section_index,
        section_title=row.section,
        document_title=row.title,
        heading_path=row.heading_path,
        chunk_index=row.chunk_index,
        document_version_id=row.document_version_id,
    )


@dataclass(frozen=True, slots=True)
class ContextAssemblyConfig:
    neighbor_window: int = 1
    max_neighbor_seeds: int = 8
    max_context_chunks: int = 24
    coverage_min_sections: int = 3
    coverage_max_chunks: int = 5


@dataclass(frozen=True, slots=True)
class RetrievalQualityDebug:
    """Deterministic RAG diagnostics (spec §18) — safe to log verbatim."""

    query_type: str
    candidate_count: int
    reranked_count: int
    unique_documents: int
    unique_sections: int
    neighbor_expansion_count: int
    coverage_expansion_count: int
    duplicate_count: int
    final_context_chunks: int
    final_context_tokens: int
    coverage_score: float


@dataclass(frozen=True, slots=True)
class ContextAssemblyResult:
    items: list[RetrievalCandidate]
    debug: RetrievalQualityDebug


def _section_key(cand: RetrievalCandidate) -> str:
    if cand.heading_path:
        return cand.heading_path
    if cand.section_title:
        return cand.section_title
    if cand.section_index is not None:
        return f"section_index:{cand.section_index}"
    return "unsectioned"


def _group_key(cand: RetrievalCandidate) -> tuple[str, str]:
    doc = str(cand.document_id) if cand.document_id else "unknown_document"
    return doc, _section_key(cand)


def _sort_key_within_group(cand: RetrievalCandidate) -> tuple[int, int]:
    if cand.chunk_index is not None:
        return (0, cand.chunk_index)
    return (1, cand.rank or 0)


def _normalize_for_dedupe(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", (text or "").strip().lower())[:160]


def _dedupe_near_duplicates(
    candidates: Sequence[RetrievalCandidate],
) -> tuple[list[RetrievalCandidate], int]:
    """Drop chunks whose normalized leading text already appeared (§15 E)."""
    seen: set[str] = set()
    out: list[RetrievalCandidate] = []
    duplicates = 0
    for cand in candidates:
        key = _normalize_for_dedupe(cand.text_snippet)
        if key and key in seen:
            duplicates += 1
            continue
        if key:
            seen.add(key)
        out.append(cand)
    return out, duplicates


async def _expand_neighbors(
    pool: list[RetrievalCandidate],
    *,
    workspace_id: UUID,
    port: ChunkContextPort | None,
    config: ContextAssemblyConfig,
) -> list[RetrievalCandidate]:
    """Pull immediate prev/next sibling chunks for the strongest seeds (§4)."""
    if port is None:
        return []
    existing_ids = {c.chunk_id for c in pool if c.chunk_id is not None}
    seeds: list[tuple[UUID, int]] = [
        (cand.document_version_id, cand.chunk_index)
        for cand in pool[: config.max_neighbor_seeds]
        if cand.document_version_id is not None and cand.chunk_index is not None
    ]
    if not seeds:
        return []
    try:
        neighbors = await port.fetch_siblings(
            workspace_id,
            seeds,
            window=config.neighbor_window,
            exclude_chunk_ids=existing_ids,
            max_total=config.max_context_chunks,
        )
    except Exception as exc:  # noqa: BLE001 — expansion is best-effort, never fatal
        logger.warning("context_assembly_neighbor_expansion_failed", error=str(exc))
        return []
    avg_score = _average_score(pool)
    for cand in neighbors:
        cand.score = round(avg_score * 0.75, 4)
    return neighbors


async def _expand_coverage(
    pool: list[RetrievalCandidate],
    *,
    workspace_id: UUID,
    query_type: QueryIntent,
    port: ChunkContextPort | None,
    config: ContextAssemblyConfig,
) -> list[RetrievalCandidate]:
    """Add representative document-coverage chunks for global questions (§7)."""
    if port is None or query_type is QueryIntent.focused:
        return []
    unique_sections = {_section_key(c) for c in pool}
    if len(unique_sections) >= config.coverage_min_sections:
        return []
    doc_versions = [c.document_version_id for c in pool if c.document_version_id is not None]
    if not doc_versions:
        return []
    dominant = max(set(doc_versions), key=doc_versions.count)
    existing_ids = {c.chunk_id for c in pool if c.chunk_id is not None}
    try:
        coverage = await port.fetch_representative(
            workspace_id, dominant, limit=config.coverage_max_chunks
        )
    except Exception as exc:  # noqa: BLE001 — coverage is best-effort, never fatal
        logger.warning("context_assembly_coverage_expansion_failed", error=str(exc))
        return []
    avg_score = _average_score(pool)
    result = []
    for cand in coverage:
        if cand.chunk_id in existing_ids:
            continue
        cand.score = round(avg_score * 0.5, 4)
        result.append(cand)
    return result


def _average_score(candidates: Sequence[RetrievalCandidate]) -> float:
    scores = [c.score for c in candidates if c.score is not None]
    return sum(scores) / len(scores) if scores else 0.0


def _lost_in_middle_order(
    groups: list[list[RetrievalCandidate]],
) -> list[list[RetrievalCandidate]]:
    """Place the strongest groups at both ends, weakest groups in the middle.

    ``groups`` must already be sorted strongest-first. Mitigates "lost in the
    middle" degradation for broad/global questions (§16).
    """
    n = len(groups)
    result: list[list[RetrievalCandidate] | None] = [None] * n
    left, right = 0, n - 1
    for i, group in enumerate(groups):
        if i % 2 == 0:
            result[left] = group
            left += 1
        else:
            result[right] = group
            right -= 1
    return [g for g in result if g is not None]


def _coverage_score(
    final: Sequence[RetrievalCandidate],
    *,
    unique_sections: int,
    reranked_count: int,
) -> float:
    """Deterministic [0,1] coverage signal (§18) — NOT an "AI quality score".

    Weighted combination of section diversity, page continuity, reranker
    relevance, and how much of the reranked pool survived into final context.
    """
    if not final:
        return 0.0
    section_diversity = min(1.0, unique_sections / max(1, min(len(final), 6)))
    pages = sorted({c.page_number for c in final if c.page_number is not None})
    if len(pages) >= 2:
        span = pages[-1] - pages[0] + 1
        page_continuity = min(1.0, len(pages) / max(1, span))
    else:
        page_continuity = 1.0 if pages else 0.5
    scores = [c.score for c in final if c.score is not None]
    reranker_relevance = min(1.0, (sum(scores) / len(scores)) if scores else 0.0)
    retained_ratio = min(1.0, len(final) / reranked_count) if reranked_count else 0.0
    return round(
        0.35 * section_diversity
        + 0.15 * page_continuity
        + 0.35 * reranker_relevance
        + 0.15 * retained_ratio,
        4,
    )


async def assemble_context(
    query_text: str,
    candidates: Sequence[RetrievalCandidate],
    *,
    workspace_id: UUID,
    port: ChunkContextPort | None = None,
    config: ContextAssemblyConfig | None = None,
    candidate_count: int = 0,
    reranked_count: int = 0,
) -> ContextAssemblyResult:
    """Assemble grounded, structure-aware context from reranked candidates.

    Pipeline: dedupe -> bounded neighbor expansion -> bounded coverage
    expansion (global questions only) -> budget trim (originals always win)
    -> group by (document, section) -> order groups -> flatten + diagnostics.
    """
    cfg = config or ContextAssemblyConfig()
    query_type = classify_query_intent(query_text)

    deduped, duplicate_count = _dedupe_near_duplicates(candidates)

    pool = list(deduped)
    existing_ids = {c.chunk_id for c in pool if c.chunk_id is not None}

    neighbors = await _expand_neighbors(pool, workspace_id=workspace_id, port=port, config=cfg)
    added_neighbors = 0
    for cand in neighbors:
        if cand.chunk_id in existing_ids:
            continue
        existing_ids.add(cand.chunk_id)
        pool.append(cand)
        added_neighbors += 1

    coverage = await _expand_coverage(
        pool, workspace_id=workspace_id, query_type=query_type, port=port, config=cfg
    )
    added_coverage = 0
    for cand in coverage:
        if cand.chunk_id in existing_ids:
            continue
        existing_ids.add(cand.chunk_id)
        pool.append(cand)
        added_coverage += 1

    # Budget trim — originals (already passed rerank) always win over expansions.
    original_ids = {c.chunk_id for c in deduped if c.chunk_id is not None}
    originals = [c for c in pool if c.chunk_id is None or c.chunk_id in original_ids]
    expansions = [c for c in pool if c.chunk_id is not None and c.chunk_id not in original_ids]
    expansions.sort(key=lambda c: c.score if c.score is not None else 0.0, reverse=True)
    budget = max(0, cfg.max_context_chunks - len(originals))
    bounded = originals + expansions[:budget]

    groups: dict[tuple[str, str], list[RetrievalCandidate]] = {}
    order: list[tuple[str, str]] = []
    for cand in bounded:
        key = _group_key(cand)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(cand)
    for key in order:
        groups[key].sort(key=_sort_key_within_group)

    ordered_groups = sorted(
        (groups[key] for key in order),
        key=lambda g: max((c.score or 0.0) for c in g),
        reverse=True,
    )
    if query_type is QueryIntent.global_overview and len(ordered_groups) > 2:
        ordered_groups = _lost_in_middle_order(ordered_groups)

    final: list[RetrievalCandidate] = [c for group in ordered_groups for c in group]

    unique_documents = len({str(c.document_id) for c in final if c.document_id})
    unique_sections = len({_group_key(c) for c in final})
    final_tokens = sum(count_tokens(c.text_snippet or "") for c in final)
    coverage_score = _coverage_score(
        final,
        unique_sections=unique_sections,
        reranked_count=reranked_count or len(candidates),
    )

    debug = RetrievalQualityDebug(
        query_type=query_type.value,
        candidate_count=candidate_count,
        reranked_count=reranked_count,
        unique_documents=unique_documents,
        unique_sections=unique_sections,
        neighbor_expansion_count=added_neighbors,
        coverage_expansion_count=added_coverage,
        duplicate_count=duplicate_count,
        final_context_chunks=len(final),
        final_context_tokens=final_tokens,
        coverage_score=coverage_score,
    )
    return ContextAssemblyResult(items=final, debug=debug)
