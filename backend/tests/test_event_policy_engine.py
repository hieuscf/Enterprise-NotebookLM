# =============================================================================
# File: test_event_policy_engine.py
# Module/Service: Event Policy Engine (FR14)
# Layer: Service
# Purpose: Unit tests for decide_agent and individual heuristics (0 LLM).
# Responsibilities:
#   - Cover ambiguous / multi-hop / structured cases + priority order
# Dependencies:
#   - pytest, app.services.event_policy.*
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: Confidence Engine, Micro Agents
# Important Notes: No Neo4j / Anthropic / DB in these tests.
# =============================================================================

from __future__ import annotations

import uuid

import pytest

from app.models.enums import AgentTriggerReason, AgentType
from app.services.event_policy.event_policy_engine import decide_agent
from app.services.event_policy.heuristics import (
    EventPolicyConfig,
    is_ambiguous_query,
    is_multi_hop_query,
    is_structured_query,
)
from app.services.retrieval.confidence_engine import RerankedItem


def _cfg(**overrides: float | int) -> EventPolicyConfig:
    base: dict[str, float | int] = {
        "ambiguous_max_tokens": 5,
        "ambiguous_score_spread_max": 0.08,
        "multi_hop_min_doc_diversity": 2,
        "multi_hop_top_k": 5,
    }
    base.update(overrides)
    return EventPolicyConfig(**base)  # type: ignore[arg-type]


def _items(*scores: float, docs: list[str] | None = None) -> list[RerankedItem]:
    out: list[RerankedItem] = []
    for i, score in enumerate(scores, start=1):
        doc = None
        if docs is not None and i - 1 < len(docs):
            doc = docs[i - 1]
        out.append(RerankedItem(rank=i, score=score, document_id=doc))
    return out


# ---------------------------------------------------------------------------
# decide_agent — required cases
# ---------------------------------------------------------------------------


def test_case1_ambiguous_cai_nay_la_gi() -> None:
    decision = decide_agent(
        "Cái này là gì?",
        _items(0.55, 0.54, 0.53),
        "complex",
        config=_cfg(),
    )
    assert decision.agent_type is AgentType.rewrite
    assert decision.trigger_reason is AgentTriggerReason.ambiguous_query


def test_case2_multi_hop_transformer_attention() -> None:
    decision = decide_agent(
        "Ảnh hưởng giữa Transformer và Attention là gì?",
        _items(0.80, 0.70, 0.60),
        "complex",
        config=_cfg(),
    )
    assert decision.agent_type is AgentType.graph
    assert decision.trigger_reason is AgentTriggerReason.multi_hop_reasoning


def test_case3_structured_pdf_count() -> None:
    decision = decide_agent(
        "Có bao nhiêu tài liệu PDF trong workspace?",
        _items(0.40, 0.30),
        "complex",
        config=_cfg(),
    )
    assert decision.agent_type is AgentType.sql
    assert decision.trigger_reason is AgentTriggerReason.structured_misclassified


def test_priority_structured_beats_multi_hop_and_ambiguous() -> None:
    # Contains both count keywords and relation-ish wording; structured wins.
    decision = decide_agent(
        "Có bao nhiêu tài liệu liên quan đến Attention?",
        _items(0.5, 0.49),
        "complex",
        config=_cfg(),
    )
    assert decision.trigger_reason is AgentTriggerReason.structured_misclassified
    assert decision.agent_type is AgentType.sql


def test_structured_ignored_when_route_not_complex() -> None:
    decision = decide_agent(
        "Có bao nhiêu tài liệu PDF trong workspace?",
        _items(0.4),
        "metadata",
        config=_cfg(),
    )
    # Not structured (route hint blocks it); falls through to ambiguous (short-ish)
    # or multi-hop. Query is long enough and has no multi-hop cue → ambiguous/fallback.
    assert decision.agent_type in {AgentType.rewrite, AgentType.graph}


# ---------------------------------------------------------------------------
# Heuristics — independent unit tests
# ---------------------------------------------------------------------------


def test_is_ambiguous_short_and_pronoun() -> None:
    cfg = _cfg()
    assert is_ambiguous_query("Cái này là gì?", [], config=cfg) is True
    assert is_ambiguous_query("Nó hoạt động thế nào?", [], config=cfg) is True
    assert is_ambiguous_query("Giải thích thêm", [], config=cfg) is True
    assert is_ambiguous_query("Cho tôi biết", [], config=cfg) is True


def test_is_ambiguous_low_score_spread() -> None:
    cfg = _cfg(ambiguous_max_tokens=2, ambiguous_score_spread_max=0.05)
    # Long query so token-length rule does not fire; near-tie spread does.
    items = _items(0.66, 0.65, 0.64, docs=[str(uuid.uuid4()), str(uuid.uuid4())])
    assert (
        is_ambiguous_query(
            "Please explain the leave policy for remote contractors in detail",
            items,
            config=cfg,
        )
        is True
    )


def test_is_multi_hop_relation_keywords() -> None:
    cfg = _cfg()
    assert (
        is_multi_hop_query(
            "Ảnh hưởng giữa Transformer và Attention là gì?",
            [],
            config=cfg,
        )
        is True
    )
    assert (
        is_multi_hop_query(
            "So sánh X với Y về hiệu năng",
            [],
            config=cfg,
        )
        is True
    )
    assert is_multi_hop_query("What is Python?", [], config=cfg) is False


def test_is_multi_hop_entity_pair_and_doc_diversity() -> None:
    cfg = _cfg(multi_hop_min_doc_diversity=2)
    doc_a, doc_b = str(uuid.uuid4()), str(uuid.uuid4())
    items = [
        RerankedItem(rank=1, score=0.9, document_id=doc_a, entity_id="e1"),
        RerankedItem(rank=2, score=0.8, document_id=doc_b, entity_id="e2"),
    ]
    assert is_multi_hop_query("Explain Foo and Bar together", items, config=cfg) is True


def test_is_structured_reuses_metadata_patterns() -> None:
    assert (
        is_structured_query(
            "Có bao nhiêu tài liệu PDF trong workspace?",
            "complex",
        )
        is True
    )
    assert is_structured_query("Danh sách tài liệu", "complex") is True
    assert is_structured_query("What is attention?", "complex") is False
    assert (
        is_structured_query(
            "Có bao nhiêu tài liệu PDF trong workspace?",
            "factoid",
        )
        is False
    )


def test_decide_agent_accepts_dict_rerank_items() -> None:
    decision = decide_agent(
        "Cái này là gì?",
        [{"rank": 1, "score": 0.5}, {"rank": 2, "score": 0.4}],
        "complex",
        config=_cfg(),
    )
    assert decision.agent_type is AgentType.rewrite
