# =============================================================================
# File: test_micro_agents.py
# Module/Service: Event-driven Micro Agents (FR14)
# Layer: Service
# Purpose: Unit tests for Rewrite / Graph / SQL agents (mocked deps).
# Responsibilities:
#   - Prove fallbacks, payloads, skip_second_retrieval, cost/model fields
# Dependencies:
#   - pytest, pytest-asyncio, agents.*
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: Event Policy Engine
# Important Notes: No live Neo4j / Anthropic / Postgres.
# =============================================================================

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.anthropic_client import AnthropicExtractionResult
from app.core.config import Settings
from app.models.enums import AgentTriggerReason, AgentType, RouteType
from app.services.event_policy.agents.graph_agent import GraphAgent
from app.services.event_policy.agents.rewrite_agent import RewriteAgent
from app.services.event_policy.agents.sql_agent import SqlAgent
from app.services.query_router.response_models import QueryRouterResult
from app.services.retrieval.confidence_engine import RerankedItem


def _settings(**overrides: Any) -> Settings:
    base = {
        "anthropic_api_key": "test-key",
        "rewrite_agent_model": "claude-3-5-haiku-latest",
        "rewrite_agent_max_tokens": 128,
        "rewrite_agent_timeout_seconds": 5.0,
        "graph_agent_max_hops": 2,
    }
    base.update(overrides)
    return Settings(**base)


def test_rewrite_agent_success_payload() -> None:
    def fake_llm(**kwargs: Any) -> AnthropicExtractionResult:
        return AnthropicExtractionResult(
            data={"rewritten_query": "What is the remote leave policy?"},
            model="claude-3-5-haiku-latest",
            input_tokens=10,
            output_tokens=8,
            estimated_cost_usd=0.0001,
        )

    agent = RewriteAgent(_settings(), llm_call=fake_llm)
    result = agent.run(
        original_query="Cái này là gì?",
        trigger_reason=AgentTriggerReason.ambiguous_query,
        confidence_score=0.4,
    )
    assert result.rewritten_query == "What is the remote leave policy?"
    assert result.event.agent_type is AgentType.rewrite
    assert result.event.model_used == "claude-3-5-haiku-latest"
    assert result.event.cost_usd == Decimal("0.0001")
    assert result.event.input_payload == {
        "original_query": "Cái này là gì?",
        "history_turns": 0,
    }
    assert result.event.output_payload == {
        "rewritten_query": "What is the remote leave policy?"
    }
    assert result.event.triggered_second_retrieval is True
    assert result.event.success is True


def test_rewrite_agent_llm_failure_returns_original() -> None:
    def boom(**kwargs: Any) -> AnthropicExtractionResult:
        raise TimeoutError("llm timeout")

    agent = RewriteAgent(_settings(), llm_call=boom)
    result = agent.run(original_query="Giải thích thêm")
    assert result.rewritten_query == "Giải thích thêm"
    assert result.event.success is False
    assert result.event.error == "TimeoutError"
    assert result.event.output_payload == {"rewritten_query": "Giải thích thêm"}


def test_graph_agent_expands_entities() -> None:
    graph = MagicMock()
    graph.expand_related_entities.return_value = [
        {"entity_id": "e2", "document_id": "d2", "hops": 1},
        {"entity_id": "e3", "document_id": "d3", "hops": 2},
    ]
    agent = GraphAgent(_settings(), graph)
    ws = uuid.uuid4()
    result = agent.run(
        workspace_id=ws,
        query_text="Ảnh hưởng giữa A và B",
        seed_entity_ids=["e1"],
        reranked_results=[RerankedItem(rank=1, score=0.9, entity_id="e1")],
    )
    assert result.expanded_entity_ids == ["e2", "e3"]
    assert set(result.expanded_document_ids) == {"d2", "d3"}
    assert result.hops == 2
    assert result.event.model_used is None
    assert result.event.cost_usd == Decimal("0")
    assert result.event.output_payload["hops"] == 2
    assert result.event.triggered_second_retrieval is True


def test_graph_agent_neo4j_error_returns_empty() -> None:
    graph = MagicMock()
    graph.expand_related_entities.side_effect = TimeoutError("neo4j")
    agent = GraphAgent(_settings(), graph)
    result = agent.run(
        workspace_id=uuid.uuid4(),
        query_text="A và B",
        seed_entity_ids=["e1"],
    )
    assert result.expanded_entity_ids == []
    assert result.expanded_document_ids == []
    assert result.event.success is False
    assert result.event.error == "TimeoutError"


@pytest.mark.asyncio
async def test_sql_agent_success_skips_second_retrieval() -> None:
    handler = MagicMock()
    handler.handle = AsyncMock(
        return_value=QueryRouterResult(
            route_type=RouteType.metadata,
            answer="Workspace có 3 tài liệu PDF.",
            citation_refs=[],
            confidence=1.0,
            verify=True,
            status=None,
            metadata={"intent": "count_pdf", "count": 3},
        )
    )
    agent = SqlAgent(handler)
    result = await agent.run(
        workspace_id=uuid.uuid4(),
        query_text="Có bao nhiêu tài liệu PDF trong workspace?",
    )
    assert result.fallback_to_complex is False
    assert result.skip_second_retrieval is True
    assert result.answer is not None
    assert result.event.agent_type is AgentType.sql
    assert result.event.model_used is None
    assert result.event.cost_usd == Decimal("0")
    assert result.event.skip_second_retrieval is True
    assert result.event.output_payload is not None
    assert "sql_result" in result.event.output_payload


@pytest.mark.asyncio
async def test_sql_agent_whitelist_miss_fallback() -> None:
    handler = MagicMock()
    handler.handle = AsyncMock(
        return_value=QueryRouterResult(
            route_type=RouteType.complex,
            answer=None,
            citation_refs=[],
            confidence=None,
            verify=False,
            status="pending_llm_pipeline",
            metadata={"fallback_reason": "unknown_metadata_intent"},
        )
    )
    agent = SqlAgent(handler)
    result = await agent.run(
        workspace_id=uuid.uuid4(),
        query_text="something unstructured",
    )
    assert result.fallback_to_complex is True
    assert result.skip_second_retrieval is False
    assert result.event.success is False
