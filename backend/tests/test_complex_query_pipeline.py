# =============================================================================
# File: test_complex_query_pipeline.py
# Module/Service: Chat Service / Complex Query Pipeline (FR14)
# Layer: Service
# Purpose: Unit tests for Confidence + Event Policy + Agents integration.
# Responsibilities:
#   - Cover HIGH/LOW rewrite/graph/sql, second-retrieval limit, llm_calls_count
# Dependencies:
#   - pytest, AsyncMock, ComplexQueryPipeline
# Public Exports:
#   - N/A
# Database/Table: N/A (fakes)
# Related Modules: confidence_engine, event_policy, agents
# Important Notes: No live Neo4j / Anthropic / Postgres.
# =============================================================================

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.models.enums import (
    AgentTriggerReason,
    AgentType,
    ConfidenceLevel,
    RouteType,
)
from app.adapters.llm_result import EmptyCompletionError
from app.services.chat.complex_query_pipeline import (
    PENDING_LLM_STATUS,
    AnswerGenerationResult,
    ComplexQueryPipeline,
)
from app.services.event_policy.agents.graph_agent import GraphAgentResult
from app.services.event_policy.agents.rewrite_agent import RewriteAgentResult
from app.services.event_policy.agents.sql_agent import SqlAgentResult
from app.services.event_policy.models import AgentEventData
from app.services.retrieval.schemas import RetrievalCandidate, RetrievalResult


def _settings(**overrides: Any) -> Settings:
    base = {
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
        "graph_agent_max_hops": 2,
        "anthropic_api_key": "test-key",
    }
    base.update(overrides)
    return Settings(**base)


def _cand(*, score: float, rank: int, doc: str | None = None) -> RetrievalCandidate:
    return RetrievalCandidate(
        workspace_id=uuid.uuid4(),
        text_snippet="snippet",
        retrieval_method="rerank",
        raw_score=score,
        document_id=uuid.UUID(doc) if doc else uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        score=score,
        rank=rank,
        source_methods=["vector"],
    )


def _result(*scores: float) -> RetrievalResult:
    items = [_cand(score=s, rank=i) for i, s in enumerate(scores, start=1)]
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
        return AnswerGenerationResult(
            answer="final answer",
            citation_refs=[],
            model_used="claude-sonnet-mock",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            cost_usd=Decimal("0.01"),
            latency_ms=50,
            verify=True,
        )


class FailingAnswerGenerator:
    """Simulates a provider call that raises instead of returning an answer
    (e.g. EmptyCompletionError from a reasoning-model empty completion)."""

    def __init__(self, exc: Exception) -> None:
        self.calls = 0
        self._exc = exc

    async def generate(self, **kwargs: Any) -> AnswerGenerationResult:
        self.calls += 1
        raise self._exc


def _pipeline(
    *,
    settings: Settings | None = None,
    hybrid: Any | None = None,
    rewrite: Any | None = None,
    graph: Any | None = None,
    sql: Any | None = None,
    answer: FakeAnswerGenerator | None = None,
    agent_events: FakeAgentEvents | None = None,
    retrieval_records: FakeRetrievalRecords | None = None,
    observability: FakeObservability | None = None,
) -> tuple[ComplexQueryPipeline, FakeAgentEvents, FakeRetrievalRecords, FakeObservability, FakeAnswerGenerator]:
    ae = agent_events or FakeAgentEvents()
    rr = retrieval_records or FakeRetrievalRecords()
    obs = observability or FakeObservability()
    ans = answer if answer is not None else FakeAnswerGenerator()
    hy = hybrid or AsyncMock(
        retrieve=AsyncMock(return_value=_result(0.97, 0.55, 0.40))
    )
    pipe = ComplexQueryPipeline(
        settings=settings or _settings(),
        hybrid=hy,
        agent_events=ae,  # type: ignore[arg-type]
        retrieval_records=rr,  # type: ignore[arg-type]
        observability=obs,  # type: ignore[arg-type]
        rewrite_agent=rewrite or MagicMock(),
        graph_agent=graph or MagicMock(),
        sql_agent=sql or MagicMock(),
        answer_generator=ans,
        retrieval_top_k=5,
    )
    return pipe, ae, rr, obs, ans


@pytest.mark.asyncio
async def test_case1_high_confidence_skips_agent_and_second_retrieval() -> None:
    rewrite = MagicMock()
    pipe, ae, rr, obs, ans = _pipeline(rewrite=rewrite)
    # Dominant top score → HIGH with default config
    initial = _result(0.97, 0.55, 0.40)
    result = await pipe.run(
        workspace_id=uuid.uuid4(),
        query_text="Explain the remote work leave policy in detail",
        message_id=uuid.uuid4(),
        initial_retrieval=initial,
        assistant_message_id=uuid.uuid4(),
    )
    assert result.confidence_level is ConfidenceLevel.high
    assert result.agent_triggered is False
    assert result.second_retrieval_executed is False
    assert ae.inserted == []
    assert rewrite.run.call_count == 0
    assert ans.calls == 1
    assert result.llm_calls_count == 1
    assert result.retrieval_pass_final == 1
    assert all(r["retrieval_pass"] == 1 for r in rr.rows)
    assert obs.generations[0]["confidence_level"] is ConfidenceLevel.high
    assert obs.generations[0]["agent_triggered"] is False


@pytest.mark.asyncio
async def test_case2_low_rewrite_second_retrieval_and_persist() -> None:
    rewrite = MagicMock()
    rewrite.run.return_value = RewriteAgentResult(
        rewritten_query="What is the remote leave policy?",
        event=AgentEventData(
            agent_type=AgentType.rewrite,
            trigger_reason=AgentTriggerReason.ambiguous_query,
            model_used="claude-3-5-haiku-latest",
            cost_usd=Decimal("0.0001"),
            latency_ms=100,
            input_payload={"original_query": "Cái này là gì?"},
            output_payload={"rewritten_query": "What is the remote leave policy?"},
            confidence_score=0.4,
            triggered_second_retrieval=True,
            skip_second_retrieval=False,
            success=True,
        ),
    )
    hybrid = AsyncMock()
    # pass1 low; pass2 still used
    hybrid.retrieve = AsyncMock(
        side_effect=[
            _result(0.66, 0.65, 0.64),  # if called
            _result(0.80, 0.50, 0.40),  # second retrieval
        ]
    )
    # Force LOW via near-tie initial
    settings = _settings(confidence_high_threshold=0.90)
    pipe, ae, rr, obs, ans = _pipeline(
        settings=settings, hybrid=hybrid, rewrite=rewrite
    )
    msg = uuid.uuid4()
    asst = uuid.uuid4()
    result = await pipe.run(
        workspace_id=uuid.uuid4(),
        query_text="Cái này là gì?",
        message_id=msg,
        initial_retrieval=_result(0.66, 0.65, 0.64),
        assistant_message_id=asst,
    )
    assert result.agent_triggered is True
    assert result.second_retrieval_executed is True
    assert result.retrieval_pass_final == 2
    assert any(r["retrieval_pass"] == 2 for r in rr.rows)
    assert len(ae.inserted) == 1
    assert ae.marked  # triggered_second_retrieval updated
    assert result.llm_calls_count == 2  # rewrite + main
    assert obs.generations[0]["confidence_score"] == result.confidence_score
    assert ans.queries[-1] == "What is the remote leave policy?"


@pytest.mark.asyncio
async def test_case3_graph_agent_marks_second_retrieval() -> None:
    graph = MagicMock()
    graph.run.return_value = GraphAgentResult(
        expanded_entity_ids=["e2"],
        expanded_document_ids=["d2"],
        hops=2,
        event=AgentEventData(
            agent_type=AgentType.graph,
            trigger_reason=AgentTriggerReason.multi_hop_reasoning,
            model_used=None,
            cost_usd=Decimal("0"),
            latency_ms=20,
            input_payload={"entities": ["e1"], "depth": 2},
            output_payload={
                "expanded_entity_ids": ["e2"],
                "expanded_document_ids": ["d2"],
                "hops": 2,
            },
            confidence_score=0.3,
            triggered_second_retrieval=True,
            skip_second_retrieval=False,
            success=True,
        ),
    )
    hybrid = AsyncMock(retrieve=AsyncMock(return_value=_result(0.7, 0.4)))
    settings = _settings(confidence_high_threshold=0.99)
    pipe, ae, rr, obs, ans = _pipeline(
        settings=settings, hybrid=hybrid, graph=graph, rewrite=MagicMock()
    )
    result = await pipe.run(
        workspace_id=uuid.uuid4(),
        query_text="Ảnh hưởng giữa Transformer và Attention là gì?",
        message_id=uuid.uuid4(),
        initial_retrieval=_result(0.5, 0.49, 0.48),
        assistant_message_id=uuid.uuid4(),
    )
    assert result.second_retrieval_executed is True
    assert ae.marked
    assert result.llm_calls_count == 1  # graph has no rewrite LLM


@pytest.mark.asyncio
async def test_case4_sql_agent_direct_zero_llm() -> None:
    sql = MagicMock()
    sql.run = AsyncMock(
        return_value=SqlAgentResult(
            sql_result={"answer": "Có 3 PDF", "count": 3},
            answer="Có 3 PDF",
            skip_second_retrieval=True,
            fallback_to_complex=False,
            event=AgentEventData(
                agent_type=AgentType.sql,
                trigger_reason=AgentTriggerReason.structured_misclassified,
                model_used=None,
                cost_usd=Decimal("0"),
                latency_ms=5,
                input_payload={},
                output_payload={"sql_result": {"answer": "Có 3 PDF"}},
                confidence_score=0.2,
                triggered_second_retrieval=False,
                skip_second_retrieval=True,
                success=True,
            ),
        )
    )
    hybrid = AsyncMock()
    settings = _settings(confidence_high_threshold=0.99)
    pipe, ae, rr, obs, ans = _pipeline(
        settings=settings, hybrid=hybrid, sql=sql, rewrite=MagicMock(), graph=MagicMock()
    )
    result = await pipe.run(
        workspace_id=uuid.uuid4(),
        query_text="Có bao nhiêu tài liệu PDF trong workspace?",
        message_id=uuid.uuid4(),
        initial_retrieval=_result(0.4, 0.3),
        assistant_message_id=uuid.uuid4(),
    )
    assert result.answer == "Có 3 PDF"
    assert result.llm_calls_count == 0
    assert result.second_retrieval_executed is False
    assert ans.calls == 0
    assert hybrid.retrieve.await_count == 0
    assert len(ae.inserted) == 1


@pytest.mark.asyncio
async def test_case5_second_retrieval_still_low_continues_to_llm_no_second_agent() -> None:
    rewrite = MagicMock()
    rewrite.run.return_value = RewriteAgentResult(
        rewritten_query="rewritten",
        event=AgentEventData(
            agent_type=AgentType.rewrite,
            trigger_reason=AgentTriggerReason.ambiguous_query,
            model_used="claude-3-5-haiku-latest",
            cost_usd=Decimal("0.0001"),
            latency_ms=10,
            input_payload={},
            output_payload={"rewritten_query": "rewritten"},
            confidence_score=0.3,
            skip_second_retrieval=False,
            success=True,
        ),
    )
    # pass2 also near-tie / low
    hybrid = AsyncMock(
        retrieve=AsyncMock(return_value=_result(0.66, 0.65, 0.64, 0.63))
    )
    settings = _settings(confidence_high_threshold=0.95)
    pipe, ae, rr, obs, ans = _pipeline(
        settings=settings, hybrid=hybrid, rewrite=rewrite
    )
    result = await pipe.run(
        workspace_id=uuid.uuid4(),
        query_text="Cái này là gì?",
        message_id=uuid.uuid4(),
        initial_retrieval=_result(0.66, 0.65, 0.64),
        assistant_message_id=uuid.uuid4(),
    )
    assert result.confidence_level is ConfidenceLevel.low
    assert result.second_retrieval_executed is True
    assert rewrite.run.call_count == 1  # no second agent loop
    assert hybrid.retrieve.await_count == 1  # only one Second Retrieval
    assert ans.calls == 1  # still goes to Prompt/LLM


@pytest.mark.asyncio
async def test_case6_provider_empty_completion_never_becomes_fake_success() -> None:
    """P0 regression: an OpenAI reasoning-model empty completion (HTTP 200,
    finish_reason=length) must surface as answer=None / pending status — never
    silently coerced into a fabricated answer — and must NOT trigger a retry
    (still exactly one main-answer LLM attempt)."""
    rewrite = MagicMock()
    ans = FailingAnswerGenerator(
        EmptyCompletionError(model="gpt-5", finish_reason="length", output_tokens=4096)
    )
    pipe, ae, rr, obs, _ = _pipeline(rewrite=rewrite, answer=ans)
    initial = _result(0.97, 0.55, 0.40)  # HIGH confidence — no agent path
    result = await pipe.run(
        workspace_id=uuid.uuid4(),
        query_text="Explain the remote work leave policy in detail",
        message_id=uuid.uuid4(),
        initial_retrieval=initial,
        assistant_message_id=uuid.uuid4(),
    )
    assert ans.calls == 1
    assert result.answer is None
    assert result.status == PENDING_LLM_STATUS
    assert result.llm_calls_count == 1  # one attempt counted, no silent retry
    assert result.citation_refs == []
    assert result.verify is False
    # message_generations still records the attempt (for cost/observability),
    # but honestly reflects failure — never a fake successful model/answer.
    assert len(obs.generations) == 1
    assert obs.generations[0]["model_used"] is None
