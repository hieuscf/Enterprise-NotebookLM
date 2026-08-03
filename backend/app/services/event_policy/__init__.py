# =============================================================================
# File: __init__.py
# Module/Service: Event Policy Engine / Micro Agents (FR14)
# Layer: Service
# Purpose: Lightweight package exports (avoid circular imports with Chat).
# Responsibilities:
#   - Re-export core symbols without pulling QueryOrchestrator cycles
# Dependencies:
#   - models, heuristics (lazy-safe)
# Public Exports:
#   - AgentDecision, AgentEventData, decide_agent, heuristic helpers
# Database/Table: N/A
# Related Modules: ComplexQueryPipeline, confidence_engine
# Important Notes: Keep this file free of Chat / Orchestrator imports.
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
