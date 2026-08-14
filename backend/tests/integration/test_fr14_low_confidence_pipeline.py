# =============================================================================
# File: test_fr14_low_confidence_pipeline.py
# Module/Service: Chat Service / FR14 Complex Query Pipeline
# Layer: Service (integration)
# Purpose: End-to-end Low Confidence cases A–D through real pipeline orchestration.
# Responsibilities:
#   - Exercise real Confidence Engine + Event Policy + ComplexQueryPipeline
#   - Mock only Hybrid / LLM / Neo4j / MetadataHandler externals
# Dependencies:
#   - pytest, ComplexQueryPipeline, RewriteAgent, GraphAgent, SqlAgent
# Public Exports:
#   - N/A
# Database/Table: N/A (fake repos)
# Related Modules: confidence_engine, event_policy_engine, agents
# Important Notes:
#   - Do NOT mock Confidence Engine / Event Policy / orchestration.
#   - Regression: HIGH confidence path still skips agents (in unit suite).
# =============================================================================

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.anthropic_client import AnthropicExtractionResult
from app.core.config import Settings
from app.core.fr14_metrics import reset_fr14_metrics_for_tests
from app.models.enums import (
    AgentTriggerReason,
    AgentType,
    ConfidenceLevel,
    RouteType,
)
from app.services.chat.complex_query_pipeline import (
    AnswerGenerationResult,
    ComplexQueryPipeline,
)
from app.services.event_policy.agents.graph_agent import GraphAgent
from app.services.event_policy.agents.rewrite_agent import RewriteAgent
from app.services.event_policy.agents.sql_agent import SqlAgent
from app.services.query_router.response_models import QueryRouterResult
from app.services.query_router.schemas import CitationRef
from app.services.retrieval.schemas import RetrievalCandidate, RetrievalResult


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "confidence_relevance_threshold": 0.65,
        "confidence_high_threshold": 0.65,
        "confidence_weight_top_score": 0.55,
        "confidence_weight_score_spread": 0.35,
        "confidence_weight_candidate_count": 0.10,
        "confidence_candidate_count_cap": 3,
        "event_policy_ambiguous_max_tokens": 5,
        "event_policy_ambiguous_score_spread_max": 0.08,
        "event_policy_multi_hop_min_doc_diversity": 2,
        "event_policy_multi_hop_top_k": 5,
        "rewrite_agent_model": "claude-3-5-haiku-latest",
        "rewrite_agent_max_tokens": 128,
        "rewrite_agent_timeout_seconds": 5.0,
        "graph_agent_max_hops": 2,
        "anthropic_api_key": "test-key",
    }
    base.update(overrides)
    return Settings(**base)


def _cand(
    *,
    score: float,
    rank: int,
    doc: uuid.UUID | None = None,
    entity: uuid.UUID | None = None,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        workspace_id=uuid.uuid4(),
        text_snippet="snippet",
        retrieval_method="rerank",
        raw_score=score,
        document_id=doc or uuid.uuid4(),
        entity_id=entity,
        chunk_id=uuid.uuid4(),
        score=score,
        rank=rank,
        source_methods=["vector"],
    )


def _result(
    *scores: float,
    docs: list[uuid.UUID] | None = None,
    entities: list[uuid.UUID] | None = None,
) -> RetrievalResult:
    items: list[RetrievalCandidate] = []
    for i, score in enumerate(scores, start=1):
        doc = docs[i - 1] if docs and i - 1 < len(docs) else None
        ent = entities[i - 1] if entities and i - 1 < len(entities) else None
        items.append(_cand(score=score, rank=i, doc=doc, entity=ent))
    return RetrievalResult(items=items, latency_ms=5, sources_used=["vector"])


class FakeAgentEvents:
    def __init__(self) -> None:
        self.inserted: list[dict[str, Any]] = []
        self.marked: list[uuid.UUID] = []

    async def insert_from_event_data(self, **kwargs: Any) -> SimpleNamespace:
        eid = uuid.uuid4()
        self.inserted.append({"id": eid, **kwargs})
        return SimpleNamespace(id=eid)

    async def mark_second_retrieval(self, event_id: uuid.UUID, *, value: bool = True) -> None:
        self.marked.append(event_id)


class FakeRetrievalRecords:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    async def insert_candidates(self, **kwargs: Any) -> int:
        self.rows.append(kwargs)
        return len(kwargs.get("candidates") or [])


class FakeObservability:
    def __init__(self) -> None:
        self.generations: list[dict[str, Any]] = []

    async def create_message_generation(self, **kwargs: Any) -> SimpleNamespace:
        gid = uuid.uuid4()
        self.generations.append({"id": gid, **kwargs})
        return SimpleNamespace(id=gid)


class FakeAnswerGenerator:
    def __init__(self) -> None:
        self.calls = 0
        self.queries: list[str] = []

    async def generate(self, **kwargs: Any) -> AnswerGenerationResult:
        self.calls += 1
        self.queries.append(kwargs["query_text"])
        retrieval = kwargs.get("retrieval_result")
        items = list(getattr(retrieval, "items", None) or [])
        refs: list[CitationRef] = []
        raw_ids: list[str] = []
        if items and getattr(items[0], "chunk_id", None) is not None:
            cand = items[0]
            raw_ids.append(str(cand.chunk_id))
            refs.append(
                CitationRef(
                    chunk_id=cand.chunk_id,
                    document_id=cand.document_id,
                    page_number=cand.page_number,
                    verify=False,
                    text_snippet=cand.text_snippet,
                )
            )
        return AnswerGenerationResult(
            answer="final answer",
            citation_refs=refs,
            raw_citation_ids=raw_ids,
            model_used="claude-sonnet-mock",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            cost_usd=Decimal("0.01"),
            latency_ms=50,
            verify=False,
        )


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_fr14_metrics_for_tests()


def _build_pipeline(
    *,
    settings: Settings,
    hybrid: Any,
    rewrite: RewriteAgent,
    graph: GraphAgent,
    sql: SqlAgent,
    answer: FakeAnswerGenerator | None = None,
) -> tuple[
    ComplexQueryPipeline,
    FakeAgentEvents,
    FakeRetrievalRecords,
    FakeObservability,
    FakeAnswerGenerator,
]:
    ae = FakeAgentEvents()
    rr = FakeRetrievalRecords()
    obs = FakeObservability()
    ans = answer or FakeAnswerGenerator()
    pipe = ComplexQueryPipeline(
        settings=settings,
        hybrid=hybrid,
        agent_events=ae,  # type: ignore[arg-type]
        retrieval_records=rr,  # type: ignore[arg-type]
        observability=obs,  # type: ignore[arg-type]
        rewrite_agent=rewrite,
        graph_agent=graph,
        sql_agent=sql,
        answer_generator=ans,
        retrieval_top_k=5,
    )
    return pipe, ae, rr, obs, ans


# ---------------------------------------------------------------------------
# Case A — Ambiguous → Rewrite → Second Retrieval → HIGH → LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_a_ambiguous_rewrite_second_retrieval_confidence_up() -> None:
    llm_calls = {"n": 0}

    def fake_llm(**_kwargs: Any) -> AnthropicExtractionResult:
        llm_calls["n"] += 1
        return AnthropicExtractionResult(
            data={"rewritten_query": "Chính sách nghỉ làm việc từ xa là gì?"},
            model="claude-3-5-haiku-latest",
            input_tokens=12,
            output_tokens=10,
            estimated_cost_usd=0.0002,
        )

    # Pass1 near-tie → LOW; Pass2 dominant → HIGH (threshold 0.70).
    settings = _settings(confidence_high_threshold=0.70)
    rewrite = RewriteAgent(settings, llm_call=fake_llm)
    neo4j = MagicMock()
    graph = GraphAgent(settings, neo4j)
    meta = MagicMock()
    meta.handle = AsyncMock()
    sql = SqlAgent(meta)

    hybrid = AsyncMock()
    # Pass 2: dominant top → confidence rises above high_threshold
    hybrid.retrieve = AsyncMock(return_value=_result(0.97, 0.40, 0.30))

    pipe, ae, rr, _obs, ans = _build_pipeline(
        settings=settings,
        hybrid=hybrid,
        rewrite=rewrite,
        graph=graph,
        sql=sql,
    )
    pass1 = _result(0.66, 0.65, 0.64)
    result = await pipe.run(
        workspace_id=uuid.uuid4(),
        query_text="Cái này là gì?",
        message_id=uuid.uuid4(),
        initial_retrieval=pass1,
        assistant_message_id=uuid.uuid4(),
    )

    assert llm_calls["n"] == 1  # Rewrite Agent once
    assert neo4j.expand_related_entities.call_count == 0
    assert meta.handle.await_count == 0
    assert len(ae.inserted) == 1
    event = ae.inserted[0]["event"]
    assert event.agent_type is AgentType.rewrite
    assert event.trigger_reason is AgentTriggerReason.ambiguous_query
    assert result.second_retrieval_executed is True
    assert ae.marked  # triggered_second_retrieval = true
    passes = {r["retrieval_pass"] for r in rr.rows}
    assert passes == {1, 2}
    assert result.confidence_score_before is not None
    assert result.confidence_score is not None
    assert result.confidence_score > result.confidence_score_before
    assert result.confidence_level is ConfidenceLevel.high
    assert ans.calls == 1
    assert result.answer == "final answer"
    assert result.llm_calls_count == 2  # rewrite Haiku + answer LLM


# ---------------------------------------------------------------------------
# Case B — Multi-hop → Graph → Neo4j → Second Retrieval → LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_b_multi_hop_graph_neo4j_second_retrieval() -> None:
    settings = _settings(confidence_high_threshold=0.99)
    rewrite = RewriteAgent(settings, llm_call=MagicMock(side_effect=AssertionError("no rewrite")))
    neo4j = MagicMock()
    neo4j.search_entities_with_chunks.return_value = [
        {"entity_id": "e1", "document_id": "d1", "name": "Transformer"},
    ]
    neo4j.expand_related_entities.return_value = [
        {"entity_id": "e2", "document_id": "d2", "hops": 1},
        {"entity_id": "e3", "document_id": "d3", "hops": 2},
    ]
    graph = GraphAgent(settings, neo4j)
    meta = MagicMock()
    meta.handle = AsyncMock()
    sql = SqlAgent(meta)

    hybrid = AsyncMock(retrieve=AsyncMock(return_value=_result(0.72, 0.40)))
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    pass1 = _result(
        0.55,
        0.54,
        0.53,
        docs=[doc_a, doc_b, doc_a],
        entities=[uuid.uuid4(), uuid.uuid4(), None],
    )

    pipe, ae, rr, _obs, ans = _build_pipeline(
        settings=settings,
        hybrid=hybrid,
        rewrite=rewrite,
        graph=graph,
        sql=sql,
    )
    result = await pipe.run(
        workspace_id=uuid.uuid4(),
        query_text="Transformer liên quan thế nào đến Attention?",
        message_id=uuid.uuid4(),
        initial_retrieval=pass1,
        assistant_message_id=uuid.uuid4(),
    )

    assert neo4j.expand_related_entities.call_count == 1
    assert len(ae.inserted) == 1
    assert ae.inserted[0]["event"].agent_type is AgentType.graph
    assert ae.inserted[0]["event"].trigger_reason is AgentTriggerReason.multi_hop_reasoning
    assert result.second_retrieval_executed is True
    passes = sorted(r["retrieval_pass"] for r in rr.rows)
    assert 1 in passes and 2 in passes
    assert result.confidence_score is not None
    assert result.confidence_score_before is not None
    # Pass-2 confidence recomputed (may still be low with high_threshold=0.99)
    assert result.agent_type == AgentType.graph.value
    assert ans.calls == 1
    assert result.llm_calls_count == 1  # graph = 0 LLM; answer = 1


# ---------------------------------------------------------------------------
# Case C — Structured → SQL → direct answer (no Prompt / answer LLM)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_c_structured_sql_direct_no_llm() -> None:
    settings = _settings(confidence_high_threshold=0.99)
    rewrite = RewriteAgent(settings, llm_call=MagicMock(side_effect=AssertionError("no rewrite")))
    neo4j = MagicMock()
    graph = GraphAgent(settings, neo4j)
    meta = MagicMock()
    meta.handle = AsyncMock(
        return_value=QueryRouterResult(
            route_type=RouteType.metadata,
            answer="Có 3 tài liệu PDF trong workspace.",
            verify=True,
            metadata={"count": 3},
        )
    )
    sql = SqlAgent(meta)
    hybrid = AsyncMock()

    pipe, ae, rr, _obs, ans = _build_pipeline(
        settings=settings,
        hybrid=hybrid,
        rewrite=rewrite,
        graph=graph,
        sql=sql,
    )
    result = await pipe.run(
        workspace_id=uuid.uuid4(),
        query_text="Có bao nhiêu tài liệu PDF trong workspace?",
        message_id=uuid.uuid4(),
        initial_retrieval=_result(0.40, 0.30),
        assistant_message_id=uuid.uuid4(),
    )

    assert meta.handle.await_count == 1
    assert len(ae.inserted) == 1
    assert ae.inserted[0]["event"].agent_type is AgentType.sql
    assert result.llm_calls_count == 0
    assert ans.calls == 0
    assert hybrid.retrieve.await_count == 0
    assert all(r["retrieval_pass"] == 1 for r in rr.rows)
    assert result.retrieval_pass_final == 1
    assert result.second_retrieval_executed is False
    assert result.answer == "Có 3 tài liệu PDF trong workspace."


# ---------------------------------------------------------------------------
# Case D — Rewrite + pass2 still LOW → still LLM, no second agent / loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_case_d_retry_still_low_no_agent_loop() -> None:
    llm_calls = {"n": 0}

    def fake_llm(**_kwargs: Any) -> AnthropicExtractionResult:
        llm_calls["n"] += 1
        return AnthropicExtractionResult(
            data={"rewritten_query": "Điều này nghĩa là gì trong tài liệu?"},
            model="claude-3-5-haiku-latest",
            input_tokens=10,
            output_tokens=8,
            estimated_cost_usd=0.0001,
        )

    settings = _settings(confidence_high_threshold=0.95)
    rewrite = RewriteAgent(settings, llm_call=fake_llm)
    neo4j = MagicMock()
    graph = GraphAgent(settings, neo4j)
    meta = MagicMock()
    meta.handle = AsyncMock()
    sql = SqlAgent(meta)

    # Pass 2 still near-tie → remains LOW
    hybrid = AsyncMock(
        retrieve=AsyncMock(return_value=_result(0.66, 0.65, 0.64, 0.63))
    )

    pipe, ae, rr, _obs, ans = _build_pipeline(
        settings=settings,
        hybrid=hybrid,
        rewrite=rewrite,
        graph=graph,
        sql=sql,
    )
    result = await pipe.run(
        workspace_id=uuid.uuid4(),
        query_text="Cái này là gì?",
        message_id=uuid.uuid4(),
        initial_retrieval=_result(0.66, 0.65, 0.64),
        assistant_message_id=uuid.uuid4(),
    )

    assert llm_calls["n"] == 1
    assert len(ae.inserted) == 1
    assert hybrid.retrieve.await_count == 1  # exactly one Second Retrieval
    assert neo4j.expand_related_entities.call_count == 0
    assert result.confidence_level is ConfidenceLevel.low
    assert result.low_confidence_after_retry is True
    assert result.metadata.get("low_confidence_after_retry") is True
    assert ans.calls == 1
    assert result.answer == "final answer"
    assert result.second_retrieval_executed is True
    passes = {r["retrieval_pass"] for r in rr.rows}
    assert passes == {1, 2}
