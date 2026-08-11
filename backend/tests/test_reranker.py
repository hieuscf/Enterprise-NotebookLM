# =============================================================================
# File: test_reranker.py
# Module/Service: Search Service / Re-ranking Layer
# Layer: Service
# Purpose: Regression test for the metadata-drop bug (RAG answer-quality P1).
# Responsibilities:
#   - Prove Reranker.rerank() preserves hierarchical/structural metadata
#     (page_number, section_index, section_title, document_title,
#     heading_path, chunk_index, document_version_id) on every candidate.
# Dependencies:
#   - pytest, pytest-asyncio, app.services.retrieval.reranker
# Database/Table: N/A
# Related Modules: HybridRetrievalService, context_assembly, prompt_builder
# Important Notes: This bug silently discarded document/section/page context
#   before it ever reached the LLM prompt — see reranker.py bugfix comment.
# =============================================================================

from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.schemas import RetrievalCandidate


def _settings(**overrides: object) -> Settings:
    base = {"reranker_backend": "heuristic"}
    base.update(overrides)
    return Settings(**base)


@pytest.mark.asyncio
async def test_rerank_preserves_hierarchical_metadata() -> None:
    workspace_id = uuid.uuid4()
    document_id = uuid.uuid4()
    document_version_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    cand = RetrievalCandidate(
        workspace_id=workspace_id,
        text_snippet="Điều 3. Quyền và nghĩa vụ của Bên A",
        retrieval_method="vector",
        raw_score=0.8,
        document_id=document_id,
        chunk_id=chunk_id,
        page_number=3,
        section_index=2,
        section_title="Điều 3",
        document_title="Hợp đồng ủy quyền",
        heading_path="HỢP ĐỒNG ỦY QUYỀN > Điều 3",
        chunk_index=17,
        document_version_id=document_version_id,
    )

    reranker = Reranker(_settings())
    ranked = await reranker.rerank("quyền và nghĩa vụ", [cand])

    assert len(ranked) == 1
    result = ranked[0]
    assert result.page_number == 3
    assert result.section_index == 2
    assert result.section_title == "Điều 3"
    assert result.document_title == "Hợp đồng ủy quyền"
    assert result.heading_path == "HỢP ĐỒNG ỦY QUYỀN > Điều 3"
    assert result.chunk_index == 17
    assert result.document_version_id == document_version_id
    assert result.retrieval_method == "rerank"


@pytest.mark.asyncio
async def test_rerank_preserves_metadata_for_multiple_candidates() -> None:
    workspace_id = uuid.uuid4()
    cands = [
        RetrievalCandidate(
            workspace_id=workspace_id,
            text_snippet=f"chunk {i}",
            retrieval_method="bm25",
            raw_score=0.5,
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            page_number=i,
            section_title=f"section-{i}",
            document_title="doc",
            heading_path=f"path-{i}",
            chunk_index=i,
            document_version_id=uuid.uuid4(),
        )
        for i in range(3)
    ]
    reranker = Reranker(_settings())
    ranked = await reranker.rerank("chunk", cands)
    assert len(ranked) == 3
    assert all(r.page_number is not None for r in ranked)
    assert all(r.section_title for r in ranked)
    assert all(r.document_title == "doc" for r in ranked)
    assert all(r.heading_path for r in ranked)
    assert all(r.chunk_index is not None for r in ranked)
    assert all(r.document_version_id is not None for r in ranked)
