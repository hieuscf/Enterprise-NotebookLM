# =============================================================================
# File: test_context_assembly.py
# Module/Service: Chat Service / Prompt Construction — Context Assembly
# Layer: Service
# Purpose: Unit tests for assemble_context() — dedup, bounded neighbor/coverage
#   expansion, grouping, lost-in-middle ordering, diagnostics (RAG P1 §4-§6,
#   §15-§18).
# Dependencies:
#   - pytest, pytest-asyncio, app.services.chat.context_assembly
# Database/Table: N/A (fake ChunkContextPort, no DB)
# Related Modules: answer_generator, prompt_builder, retrieval.reranker
# =============================================================================

from __future__ import annotations

import uuid
from uuid import UUID

import pytest

from app.services.chat.context_assembly import (
    ContextAssemblyConfig,
    assemble_context,
)
from app.services.retrieval.schemas import RetrievalCandidate

WORKSPACE_ID = uuid.uuid4()
DOC_ID = uuid.uuid4()
DOC_VERSION_ID = uuid.uuid4()


def _cand(
    *,
    text: str,
    chunk_index: int,
    score: float = 0.5,
    section_title: str | None = "Điều 1",
    page_number: int | None = 1,
    document_id: UUID | None = None,
    document_version_id: UUID | None = None,
    document_title: str = "Hợp đồng ủy quyền",
    heading_path: str | None = None,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        workspace_id=WORKSPACE_ID,
        text_snippet=text,
        retrieval_method="rerank",
        raw_score=score,
        score=score,
        document_id=document_id or DOC_ID,
        chunk_id=uuid.uuid4(),
        page_number=page_number,
        section_title=section_title,
        document_title=document_title,
        heading_path=heading_path or section_title,
        chunk_index=chunk_index,
        document_version_id=document_version_id or DOC_VERSION_ID,
    )


class FakeContextPort:
    """Deterministic fake ChunkContextPort for tests — no DB."""

    def __init__(
        self,
        siblings: list[RetrievalCandidate] | None = None,
        representative: list[RetrievalCandidate] | None = None,
    ) -> None:
        self.siblings = siblings or []
        self.representative = representative or []
        self.fetch_siblings_calls = 0
        self.fetch_representative_calls = 0

    async def fetch_siblings(
        self,
        workspace_id: UUID,
        seeds: list[tuple[UUID, int]],
        *,
        window: int,
        exclude_chunk_ids: set[UUID],
        max_total: int,
    ) -> list[RetrievalCandidate]:
        self.fetch_siblings_calls += 1
        return [c for c in self.siblings if c.chunk_id not in exclude_chunk_ids]

    async def fetch_representative(
        self,
        workspace_id: UUID,
        document_version_id: UUID,
        *,
        limit: int,
    ) -> list[RetrievalCandidate]:
        self.fetch_representative_calls += 1
        return self.representative[:limit]


@pytest.mark.asyncio
async def test_dedupes_near_identical_chunks() -> None:
    a = _cand(text="Bên A cam kết thực hiện đúng nghĩa vụ.", chunk_index=1)
    b = _cand(text="Bên A cam kết thực hiện đúng nghĩa vụ.", chunk_index=2)
    result = await assemble_context(
        "Ai là bên A?", [a, b], workspace_id=WORKSPACE_ID, reranked_count=2
    )
    assert len(result.items) == 1
    assert result.debug.duplicate_count == 1


@pytest.mark.asyncio
async def test_no_port_means_no_expansion() -> None:
    a = _cand(text="chunk one content", chunk_index=1)
    result = await assemble_context(
        "Nội dung chính của tài liệu", [a], workspace_id=WORKSPACE_ID, port=None, reranked_count=1
    )
    assert result.debug.neighbor_expansion_count == 0
    assert result.debug.coverage_expansion_count == 0
    assert len(result.items) == 1


@pytest.mark.asyncio
async def test_neighbor_expansion_adds_siblings_with_decayed_score() -> None:
    seed = _cand(text="Điều 2. Nội dung chính", chunk_index=5, score=0.9)
    sibling = _cand(text="Bên B thực hiện phân phối phần mềm.", chunk_index=6, score=0.0)
    port = FakeContextPort(siblings=[sibling])

    result = await assemble_context(
        "Ai là bên A?",
        [seed],
        workspace_id=WORKSPACE_ID,
        port=port,
        reranked_count=1,
    )

    assert port.fetch_siblings_calls == 1
    assert result.debug.neighbor_expansion_count == 1
    assert len(result.items) == 2
    added = next(c for c in result.items if c.chunk_id == sibling.chunk_id)
    assert added.score == pytest.approx(0.9 * 0.75, rel=1e-3)


@pytest.mark.asyncio
async def test_coverage_expansion_only_for_global_queries_with_low_diversity() -> None:
    seed = _cand(text="chunk about scope", chunk_index=1, section_title="Điều 1")
    coverage_chunk = _cand(text="Representative heading chunk", chunk_index=99)
    port = FakeContextPort(representative=[coverage_chunk])

    # Focused query -> no coverage expansion even with a port available.
    focused_result = await assemble_context(
        "Ai là bên A?", [seed], workspace_id=WORKSPACE_ID, port=port, reranked_count=1
    )
    assert focused_result.debug.coverage_expansion_count == 0
    assert port.fetch_representative_calls == 0

    # Global query with only 1 unique section (< coverage_min_sections) -> expand.
    global_result = await assemble_context(
        "Nội dung chính của tài liệu",
        [seed],
        workspace_id=WORKSPACE_ID,
        port=port,
        reranked_count=1,
    )
    assert global_result.debug.coverage_expansion_count == 1
    assert port.fetch_representative_calls == 1
    assert any(c.chunk_id == coverage_chunk.chunk_id for c in global_result.items)


@pytest.mark.asyncio
async def test_coverage_expansion_skipped_when_sections_already_diverse() -> None:
    cands = [
        _cand(text=f"chunk {i}", chunk_index=i, section_title=f"Điều {i}")
        for i in range(1, 5)
    ]
    coverage_chunk = _cand(text="Representative heading chunk", chunk_index=99)
    port = FakeContextPort(representative=[coverage_chunk])

    result = await assemble_context(
        "Nội dung chính của tài liệu",
        cands,
        workspace_id=WORKSPACE_ID,
        port=port,
        config=ContextAssemblyConfig(coverage_min_sections=3),
        reranked_count=len(cands),
    )
    assert result.debug.coverage_expansion_count == 0


@pytest.mark.asyncio
async def test_originals_always_survive_budget_trim_over_expansions() -> None:
    originals = [_cand(text=f"orig {i}", chunk_index=i, score=0.9) for i in range(3)]
    sibling = _cand(text="low value sibling", chunk_index=50, score=0.01)
    port = FakeContextPort(siblings=[sibling])
    config = ContextAssemblyConfig(max_context_chunks=3)

    result = await assemble_context(
        "Ai là bên A?",
        originals,
        workspace_id=WORKSPACE_ID,
        port=port,
        config=config,
        reranked_count=3,
    )
    original_ids = {c.chunk_id for c in originals}
    assert all(c.chunk_id in original_ids for c in result.items)
    assert len(result.items) == 3


@pytest.mark.asyncio
async def test_groups_by_document_and_section() -> None:
    doc_b = uuid.uuid4()
    a1 = _cand(text="a1", chunk_index=1, section_title="Điều 1", score=0.9)
    a2 = _cand(text="a2", chunk_index=2, section_title="Điều 1", score=0.8)
    b1 = _cand(
        text="b1",
        chunk_index=1,
        section_title="Điều 1",
        document_id=doc_b,
        document_version_id=uuid.uuid4(),
        score=0.5,
    )
    result = await assemble_context(
        "Ai là bên A?", [a1, b1, a2], workspace_id=WORKSPACE_ID, reranked_count=3
    )
    # Same-document/section chunks stay adjacent (grouped), ordered by chunk_index.
    ids_in_order = [c.chunk_id for c in result.items]
    assert ids_in_order.index(a1.chunk_id) < ids_in_order.index(a2.chunk_id)


@pytest.mark.asyncio
async def test_lost_in_middle_ordering_for_global_queries_with_many_groups() -> None:
    groups = []
    for i in range(4):
        groups.append(
            _cand(
                text=f"group {i}",
                chunk_index=i,
                section_title=f"Điều {i}",
                score=1.0 - (i * 0.2),
            )
        )
    result = await assemble_context(
        "Nội dung chính của tài liệu",
        groups,
        workspace_id=WORKSPACE_ID,
        reranked_count=len(groups),
    )
    # Strongest group (score 1.0) should be first; second-strongest at the end,
    # not buried in the middle.
    assert result.items[0].text_snippet == "group 0"
    assert result.items[-1].text_snippet == "group 1"


@pytest.mark.asyncio
async def test_debug_metrics_reported() -> None:
    cands = [_cand(text=f"c{i}", chunk_index=i) for i in range(4)]
    result = await assemble_context(
        "Ai là bên A?",
        cands,
        workspace_id=WORKSPACE_ID,
        candidate_count=10,
        reranked_count=4,
    )
    debug = result.debug
    assert debug.query_type == "focused"
    assert debug.candidate_count == 10
    assert debug.reranked_count == 4
    assert debug.final_context_chunks == len(result.items)
    assert 0.0 <= debug.coverage_score <= 1.0
    assert debug.unique_documents == 1
