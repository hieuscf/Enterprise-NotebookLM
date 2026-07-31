# =============================================================================
# File: test_hybrid_retrieval.py
# Module/Service: Search Service / Hybrid Retrieval
# Layer: Service
# Purpose: Unit tests for Hybrid Retrieval orchestration (FR3 / Part 1).
# Responsibilities:
#   - Prove parallel fan-out, partial failure tolerance, dedupe, all-fail error
# Dependencies:
#   - pytest, pytest-asyncio, app.services.retrieval.*
# Public Exports:
#   - N/A
# Database/Table: N/A (all adapters mocked)
# Related Modules: HybridRetrievalService, Reranker
# Important Notes: No live Qdrant/ES/Neo4j/Postgres in CI.
# =============================================================================

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.services.retrieval.bm25_search import Bm25Search
from app.services.retrieval.exceptions import RetrievalUnavailableError
from app.services.retrieval.graph_search import GraphSearch
from app.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.schemas import RetrievalCandidate
from app.services.retrieval.vector_search import VectorSearch


def _settings(**overrides: Any) -> Settings:
    base = {
        "embedding_model_name": "local-hash-embedding-v1",
        "embedding_dimension": 8,
        "embedding_provider": "local",
        "retrieval_vector_timeout_seconds": 2.0,
        "retrieval_bm25_timeout_seconds": 2.0,
        "retrieval_graph_timeout_seconds": 2.0,
        "retrieval_per_source_top_k": 20,
        "retrieval_max_rerank_candidates": 100,
        "reranker_backend": "heuristic",
    }
    base.update(overrides)
    return Settings(**base)


def _cand(
    workspace_id: uuid.UUID,
    *,
    chunk_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    method: str = "vector",
    raw_score: float = 0.5,
    text: str = "relevant policy text about leave",
) -> RetrievalCandidate:
    return RetrievalCandidate(
        workspace_id=workspace_id,
        chunk_id=chunk_id or uuid.uuid4(),
        document_id=document_id or uuid.uuid4(),
        text_snippet=text,
        raw_score=raw_score,
        retrieval_method=method,
        source_methods=[method],
    )


def _build_service(
    settings: Settings,
    *,
    vector: VectorSearch | AsyncMock,
    bm25: Bm25Search | AsyncMock,
    graph: GraphSearch | AsyncMock,
) -> HybridRetrievalService:
    return HybridRetrievalService(
        settings=settings,
        vector_search=vector,  # type: ignore[arg-type]
        bm25_search=bm25,  # type: ignore[arg-type]
        graph_search=graph,  # type: ignore[arg-type]
        reranker=Reranker(settings),
    )


@pytest.mark.asyncio
async def test_retrieve_returns_ranked_nonempty_results(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = uuid.uuid4()
    settings = _settings()
    c1 = _cand(workspace_id, method="vector", raw_score=0.9, text="annual leave policy days")
    c2 = _cand(workspace_id, method="bm25", raw_score=0.8, text="sick leave entitlement")
    c3 = _cand(workspace_id, method="knowledge_graph", raw_score=0.7, text="HR leave entity")

    vector = AsyncMock()
    vector.search = AsyncMock(return_value=[c1])
    bm25 = AsyncMock()
    bm25.search = AsyncMock(return_value=[c2])
    graph = AsyncMock()
    graph.search = AsyncMock(return_value=[c3])

    async def _fake_embed(_self: HybridRetrievalService, _q: str) -> list[float]:
        return [0.1] * 8

    monkeypatch.setattr(HybridRetrievalService, "_embed_once", _fake_embed)
    svc = _build_service(settings, vector=vector, bm25=bm25, graph=graph)
    result = await svc.retrieve(workspace_id, "leave policy", top_k=10)

    assert result.items
    assert len(result.items) == 3
    ranks = [item.rank for item in result.items]
    assert ranks == sorted(ranks)
    assert ranks == list(range(1, len(ranks) + 1))
    assert all(item.score is not None and item.score >= 0 for item in result.items)
    chunk_ids = [item.chunk_id for item in result.items]
    assert len(chunk_ids) == len(set(chunk_ids))
    assert set(result.sources_used) == {"vector", "bm25", "graph"}
    assert all(item.retrieval_method == "rerank" for item in result.items)


@pytest.mark.asyncio
async def test_neo4j_failure_still_returns_vector_and_bm25(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id = uuid.uuid4()
    settings = _settings()
    vector = AsyncMock()
    vector.search = AsyncMock(
        return_value=[_cand(workspace_id, method="vector", text="vector hit leave")]
    )
    bm25 = AsyncMock()
    bm25.search = AsyncMock(
        return_value=[_cand(workspace_id, method="bm25", text="bm25 hit leave")]
    )
    graph = AsyncMock()
    graph.search = AsyncMock(side_effect=RuntimeError("Neo4j down"))

    async def _fake_embed(_self: HybridRetrievalService, _q: str) -> list[float]:
        return [0.2] * 8

    monkeypatch.setattr(HybridRetrievalService, "_embed_once", _fake_embed)
    svc = _build_service(settings, vector=vector, bm25=bm25, graph=graph)
    result = await svc.retrieve(workspace_id, "leave", top_k=5)

    assert "graph" not in result.sources_used
    assert "vector" in result.sources_used
    assert "bm25" in result.sources_used
    assert len(result.items) >= 1


@pytest.mark.asyncio
async def test_vector_timeout_bm25_and_graph_continue(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = uuid.uuid4()
    settings = _settings(retrieval_vector_timeout_seconds=0.05)

    async def _slow_vector(*_args: Any, **_kwargs: Any) -> list[RetrievalCandidate]:
        await asyncio.sleep(0.2)
        return [_cand(workspace_id, method="vector")]

    vector = AsyncMock()
    vector.search = _slow_vector
    bm25 = AsyncMock()
    bm25.search = AsyncMock(
        return_value=[_cand(workspace_id, method="bm25", text="bm25 leave")]
    )
    graph = AsyncMock()
    graph.search = AsyncMock(
        return_value=[_cand(workspace_id, method="knowledge_graph", text="graph leave")]
    )

    async def _fake_embed(_self: HybridRetrievalService, _q: str) -> list[float]:
        return [0.3] * 8

    monkeypatch.setattr(HybridRetrievalService, "_embed_once", _fake_embed)
    svc = _build_service(settings, vector=vector, bm25=bm25, graph=graph)
    result = await svc.retrieve(workspace_id, "leave", top_k=5)

    assert "vector" not in result.sources_used
    assert "bm25" in result.sources_used
    assert "graph" in result.sources_used
    assert result.timings.get("vector_ms") is not None


@pytest.mark.asyncio
async def test_all_sources_fail_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = uuid.uuid4()
    settings = _settings()
    vector = AsyncMock()
    vector.search = AsyncMock(side_effect=RuntimeError("qdrant"))
    bm25 = AsyncMock()
    bm25.search = AsyncMock(side_effect=RuntimeError("es"))
    graph = AsyncMock()
    graph.search = AsyncMock(side_effect=RuntimeError("neo4j"))

    async def _fake_embed(_self: HybridRetrievalService, _q: str) -> list[float]:
        return [0.4] * 8

    monkeypatch.setattr(HybridRetrievalService, "_embed_once", _fake_embed)
    svc = _build_service(settings, vector=vector, bm25=bm25, graph=graph)

    with pytest.raises(RetrievalUnavailableError):
        await svc.retrieve(workspace_id, "anything", top_k=5)


@pytest.mark.asyncio
async def test_duplicate_chunk_merged_before_rerank(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = uuid.uuid4()
    settings = _settings()
    chunk_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    vector_hit = _cand(
        workspace_id,
        chunk_id=chunk_id,
        document_id=doc_id,
        method="vector",
        raw_score=0.55,
        text="shared chunk about leave policy",
    )
    bm25_hit = _cand(
        workspace_id,
        chunk_id=chunk_id,
        document_id=doc_id,
        method="bm25",
        raw_score=0.95,
        text="shared chunk about leave policy",
    )

    vector = AsyncMock()
    vector.search = AsyncMock(return_value=[vector_hit])
    bm25 = AsyncMock()
    bm25.search = AsyncMock(return_value=[bm25_hit])
    graph = AsyncMock()
    graph.search = AsyncMock(return_value=[])

    async def _fake_embed(_self: HybridRetrievalService, _q: str) -> list[float]:
        return [0.5] * 8

    monkeypatch.setattr(HybridRetrievalService, "_embed_once", _fake_embed)
    svc = _build_service(settings, vector=vector, bm25=bm25, graph=graph)
    result = await svc.retrieve(workspace_id, "leave policy", top_k=10)

    assert len(result.items) == 1
    item = result.items[0]
    assert item.chunk_id == chunk_id
    assert item.raw_score == pytest.approx(0.95)
    assert set(item.source_methods) == {"vector", "bm25"}
    assert item.retrieval_method == "rerank"
    assert item.rank == 1
    assert item.score is not None
