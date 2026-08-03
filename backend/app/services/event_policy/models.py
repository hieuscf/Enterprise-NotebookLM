# =============================================================================
# File: models.py
# Module/Service: Event Policy Engine / Micro Agents (FR14)
# Layer: Service
# Purpose: Shared Pydantic models for AgentDecision and AgentEventData.
# Responsibilities:
#   - AgentDecision: Event Policy output (trigger_reason → agent_type)
#   - AgentEventData: audit payload aligned with agent_events table (Part 4 INSERT)
# Dependencies:
#   - pydantic, app.models.enums
# Public Exports:
#   - AgentDecision, AgentEventData, ChatTurn
# Database/Table: agent_events (shape only — persistence in Part 4)
# Related Modules: event_policy_engine, agents.*
# Important Notes: Fields mirror AgentEvent ORM; Part 4 maps 1:1 without remapping.
# =============================================================================

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AgentTriggerReason, AgentType


class ChatTurn(BaseModel):
    """Minimal conversation turn passed into Rewrite Agent (no DB access)."""

    model_config = ConfigDict(extra="ignore")

    role: str
    content: str


class AgentDecision(BaseModel):
    """Rule-based decision from Event Policy Engine."""

    model_config = ConfigDict(frozen=True)

    trigger_reason: AgentTriggerReason
    agent_type: AgentType


class AgentEventData(BaseModel):
    """Audit trail struct matching ``agent_events`` columns for Part 4 INSERT."""

    model_config = ConfigDict(frozen=True)

    agent_type: AgentType
    trigger_reason: AgentTriggerReason
    model_used: str | None = None
    cost_usd: Decimal = Field(default=Decimal("0"))
    latency_ms: int = Field(ge=0)
    input_payload: dict[str, Any] | None = None
    output_payload: dict[str, Any] | None = None
    confidence_score: float | None = None
    triggered_second_retrieval: bool = False
    # Pipeline hints (not DB columns — Part 4 / orchestrator consume these)
    skip_second_retrieval: bool = False
    success: bool = True
    error: str | None = None
