# =============================================================================
# File: __init__.py
# Module/Service: Event Policy Engine / Micro Agents (FR14)
# Layer: Service
# Purpose: Package exports for Event Policy + agent orchestration helpers.
# Responsibilities:
#   - Expose decide_agent, AgentDecision, AgentEventData, agent classes
# Dependencies:
#   - event_policy_engine, heuristics, models, agents.*
# Public Exports:
#   - decide_agent, AgentDecision, AgentEventData, heuristics, agents
# Database/Table: N/A
# Related Modules: confidence_engine, Chat Service (Part 4)
# Important Notes: 0 LLM in Event Policy itself; Rewrite Agent may call Haiku.
# =============================================================================

from app.services.event_policy.event_policy_engine import decide_agent
from app.services.event_policy.heuristics import (
    EventPolicyConfig,
    build_event_policy_config,
    is_ambiguous_query,
    is_multi_hop_query,
    is_structured_query,
)
from app.services.event_policy.models import AgentDecision, AgentEventData, ChatTurn

__all__ = [
    "AgentDecision",
    "AgentEventData",
    "ChatTurn",
    "EventPolicyConfig",
    "build_event_policy_config",
    "decide_agent",
    "is_ambiguous_query",
    "is_multi_hop_query",
    "is_structured_query",
]
