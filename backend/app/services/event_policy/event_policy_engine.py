# =============================================================================
# File: event_policy_engine.py
# Module/Service: Event Policy Engine (FR14)
# Layer: Service
# Purpose: Rule-based selector mapping Low Confidence → Micro Agent.
# Responsibilities:
#   - Orchestrate structured / multi-hop / ambiguous heuristics
#   - Emit AgentDecision (trigger_reason + agent_type)
# Dependencies:
#   - heuristics, models, MetadataPatternRegistry
# Public Exports:
#   - decide_agent
# Database/Table: N/A
# Related Modules: confidence_engine, agents.*, Chat Service (Part 4)
# Important Notes:
#   - 0 LLM / 0 embedding / 0 Neo4j. Priority: structured > multi_hop > ambiguous.
#   - Called only after Confidence Engine returns low (orchestrator gate).
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence

from app.core.logging import get_logger
from app.models.enums import AgentTriggerReason, AgentType
from app.services.event_policy.heuristics import (
    EventPolicyConfig,
    is_ambiguous_query,
    is_multi_hop_query,
    is_structured_query,
)
from app.services.event_policy.models import AgentDecision
from app.services.query_router.metadata_patterns import MetadataPatternRegistry
from app.services.retrieval.confidence_engine import RerankedItem

logger = get_logger(__name__)

# Explicit priority order (highest first) — do not reorder casually.
_PRIORITY: tuple[AgentTriggerReason, ...] = (
    AgentTriggerReason.structured_misclassified,
    AgentTriggerReason.multi_hop_reasoning,
    AgentTriggerReason.ambiguous_query,
)

_TRIGGER_TO_AGENT: dict[AgentTriggerReason, AgentType] = {
    AgentTriggerReason.structured_misclassified: AgentType.sql,
    AgentTriggerReason.multi_hop_reasoning: AgentType.graph,
    AgentTriggerReason.ambiguous_query: AgentType.rewrite,
}


def decide_agent(
    query_text: str,
    reranked_results: Sequence[RerankedItem | dict[str, object]],
    route_type_hint: str,
    *,
    config: EventPolicyConfig | None = None,
    pattern_registry: MetadataPatternRegistry | None = None,
) -> AgentDecision:
    """Select Micro Agent from heuristics (pure orchestration, no side effects).

    Priority when multiple rules match:
      1. structured_misclassified → sql
      2. multi_hop_reasoning → graph
      3. ambiguous_query → rewrite

    If none match, fall back to ``ambiguous_query`` / ``rewrite`` (safe default
    under Low Confidence).

    Args:
        query_text: Original user question.
        reranked_results: Post Cross-Encoder candidates (score/rank[/document_id]).
        route_type_hint: Router label (``complex`` expected when this runs).
        config: Heuristic thresholds from Settings (optional → Settings defaults).
        pattern_registry: Optional MetadataPatternRegistry (tests / DI).

    Returns:
        ``AgentDecision`` with ``trigger_reason`` and ``agent_type``.
    """
    from app.core.config import get_settings
    from app.services.event_policy.heuristics import build_event_policy_config

    cfg = config or build_event_policy_config(get_settings())
    items = [
        item if isinstance(item, RerankedItem) else RerankedItem.model_validate(item)
        for item in reranked_results
    ]
    registry = pattern_registry or MetadataPatternRegistry()

    if is_structured_query(query_text, route_type_hint, pattern_registry=registry):
        decision = _decision(AgentTriggerReason.structured_misclassified)
        _log(decision, query_len=len(query_text or ""))
        return decision

    if is_multi_hop_query(query_text, items, config=cfg):
        decision = _decision(AgentTriggerReason.multi_hop_reasoning)
        _log(decision, query_len=len(query_text or ""))
        return decision

    if is_ambiguous_query(query_text, items, config=cfg):
        decision = _decision(AgentTriggerReason.ambiguous_query)
        _log(decision, query_len=len(query_text or ""))
        return decision

    decision = _decision(AgentTriggerReason.ambiguous_query)
    _log(decision, query_len=len(query_text or ""), fallback=True)
    return decision


def _decision(reason: AgentTriggerReason) -> AgentDecision:
    return AgentDecision(
        trigger_reason=reason,
        agent_type=_TRIGGER_TO_AGENT[reason],
    )


def _log(decision: AgentDecision, *, query_len: int, fallback: bool = False) -> None:
    logger.info(
        "event_policy_decision",
        trigger_reason=decision.trigger_reason.value,
        agent_type=decision.agent_type.value,
        query_len=query_len,
        fallback=fallback,
        priority=[r.value for r in _PRIORITY],
    )
