# =============================================================================
# File: chat.py
# Module/Service: Chat Service
# Layer: Schema
# Purpose: Pydantic response models for Chat FR14 agent-events API.
# Responsibilities:
#   - AgentEventResponse matching OpenAPI AgentEvent (no payloads)
# Dependencies:
#   - pydantic
# Public Exports:
#   - AgentEventResponse
# Database/Table: agent_events (read projection)
# Related Modules: Enterprise_notebooklm_openapi.yaml AgentEvent
# Important Notes: input_payload / output_payload intentionally omitted.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentEventResponse(BaseModel):
    """Public AgentEvent DTO — excludes sensitive JSON payloads."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_type: Literal["rewrite", "graph", "sql"]
    trigger_reason: Literal[
        "ambiguous_query",
        "multi_hop_reasoning",
        "structured_misclassified",
    ]
    confidence_score: float | None = None
    triggered_second_retrieval: bool
    model_used: str | None = None
    cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)
    created_at: datetime
