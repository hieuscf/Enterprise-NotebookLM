# =============================================================================
# File: test_query_router.py
# Module/Service: Query Router (FR11)
# Layer: Service
# Purpose: Unit tests for direct-to-complex routing (no cache check).
# Responsibilities:
#   - Every query → route_type=complex immediately; no cache lookup; no LLM
# Dependencies:
#   - pytest, AsyncMock, app.services.query_router.*
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: QueryRouter, RuleBasedClassifier
# Important Notes: 0 live Qdrant/Postgres/LLM in CI.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.config.router_rules import RouterRules, build_router_rules
from app.core.config import Settings
from app.models.enums import RouteType
from app.services.query_router.cache import (
    build_normalized_query,
    hash_query,
    normalize_query,
)
from app.services.query_router.classifier import (
    RuleBasedClassifier,
    build_rule_based_classifier,
)
from app.services.query_router.router import QueryRouter
from app.services.retrieval.schemas import RetrievalCandidate, RetrievalResult

# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


def _settings(**overrides: Any) -> Settings:
    base = {
        "embedding_model_name": "local-hash-embedding-v1",
        "embedding_dimension": 8,
        "embedding_provider": "local",
        "query_cache_similarity_threshold": 0.90,
        "query_router_factoid_confidence_threshold": 0.75,
        "query_router_minimum_factoid_score": 0.70,
        "query_router_maximum_factoid_length": 80,
        "query_router_factoid_top_k": 1,
        "query_router_classifier_confidence_threshold": 0.12,
        "query_router_classifier_margin_threshold": 0.03,
        "query_router_classifier_embedding_dimension": 256,
        "reranker_backend": "heuristic",
    }
    base.update(overrides)
    return Settings(**base)


def _rules(settings: Settings | None = None) -> RouterRules:
    return build_router_rules(settings or _settings())


def _retrieval(workspace_id: uuid.UUID, score: float, text: str = "snippet") -> RetrievalResult:
    return RetrievalResult(
        items=[
            RetrievalCandidate(
                workspace_id=workspace_id,
                document_id=uuid.uuid4(),
                chunk_id=uuid.uuid4(),
                text_snippet=text,
                retrieval_method="rerank",
                raw_score=score,
                score=score,
                rank=1,
                source_methods=["vector"],
            )
        ],
        latency_ms=5,
        sources_used=["vector"],
        timings={},
    )


def _build_router(
    *,
    settings: Settings | None = None,
    hybrid: AsyncMock | None = None,
) -> tuple[QueryRouter, AsyncMock]:
    settings = settings or _settings()
    rules = _rules(settings)
    if hybrid is None:
        hybrid = AsyncMock()
        hybrid.retrieve = AsyncMock(
            return_value=RetrievalResult(items=[], latency_ms=1, sources_used=[], timings={})
        )
    router = QueryRouter(
        rules=rules,
        classifier=build_rule_based_classifier(settings),
        hybrid=hybrid,
    )
    return router, hybrid


# ---------------------------------------------------------------------------
# Normalize / hash
# ---------------------------------------------------------------------------


def test_normalize_and_hash_stable() -> None:
    a = normalize_query("  Hello,   WORLD!!! ")
    b = normalize_query("hello world")
    assert a == b == "hello world"
    assert hash_query(a) == hash_query(b)


# ---------------------------------------------------------------------------
# Every query — regardless of former metadata/factoid/complex classification —
# now routes directly to complex, with no cache lookup at all.
# ---------------------------------------------------------------------------

FORMER_METADATA_SAMPLES = [
    "Có bao nhiêu tài liệu?",
    "Danh sách PDF",
    "Liệt kê tài liệu",
    "How many documents are there?",
    "Show all files in the workspace",
    "Thống kê số lượng tài liệu theo loại",
]

FORMER_FACTOID_SAMPLES = [
    "AI là gì?",
    "Tác giả là ai?",
    "Khi nào ban hành?",
    "What is RAG?",
    "Who is the author?",
]

COMPLEX_SAMPLES = [
    "So sánh hai chính sách nghỉ phép năm 2023 và 2024",
    "Phân tích ưu nhược điểm của kiến trúc RAG hiện tại",
    "Tóm tắt toàn bộ tài liệu và đưa ra khuyến nghị",
    "Compare the onboarding processes across departments in detail",
    "Analyze multi-hop relationships between entities and summarize risks",
]

ALL_SAMPLES = FORMER_METADATA_SAMPLES + FORMER_FACTOID_SAMPLES + COMPLEX_SAMPLES


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ALL_SAMPLES)
async def test_every_query_routes_directly_to_complex(query: str) -> None:
    workspace_id = uuid.uuid4()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, 0.95))
    router, hybrid_out = _build_router(hybrid=hybrid)
    decision = await router.route(workspace_id, uuid.uuid4(), query)
    assert decision.route_type == RouteType.complex
    assert decision.reason == "direct_complex"
    assert decision.cache_entry is None
    # ComplexQueryPipeline owns hybrid retrieval — router must not probe.
    hybrid_out.retrieve.assert_not_awaited()
    assert decision.retrieval_result is None


@pytest.mark.asyncio
async def test_classifier_not_used_for_routing() -> None:
    workspace_id = uuid.uuid4()
    router, _ = _build_router()
    with patch.object(
        RuleBasedClassifier, "classify_detailed", autospec=True
    ) as classify_spy:
        decision = await router.route(
            workspace_id, uuid.uuid4(), "Có bao nhiêu tài liệu?"
        )
        assert decision.route_type == RouteType.complex
        classify_spy.assert_not_called()


@pytest.mark.asyncio
async def test_repeated_query_never_hits_cache() -> None:
    """No query_cache lookup happens anymore — identical queries always go direct."""
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    query = "What is the leave policy?"
    router, hybrid = _build_router()

    first = await router.route(workspace_id, user_id, query)
    second = await router.route(workspace_id, user_id, query)

    for decision in (first, second):
        assert decision.route_type == RouteType.complex
        assert decision.reason == "direct_complex"
        assert decision.cache_entry is None
    hybrid.retrieve.assert_not_awaited()


# ---------------------------------------------------------------------------
# No LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_never_calls_llm() -> None:
    workspace_id = uuid.uuid4()
    hybrid = AsyncMock()
    hybrid.retrieve = AsyncMock(return_value=_retrieval(workspace_id, 0.95))
    router, _ = _build_router(hybrid=hybrid)
    with patch(
        "app.adapters.anthropic_client.extract_structured_json",
        autospec=True,
    ) as llm_spy:
        await router.route(workspace_id, uuid.uuid4(), "AI là gì?")
        await router.route(workspace_id, uuid.uuid4(), "Có bao nhiêu tài liệu?")
        await router.route(
            workspace_id,
            uuid.uuid4(),
            "So sánh chi tiết hai phương án triển khai hệ thống",
        )
        llm_spy.assert_not_called()
