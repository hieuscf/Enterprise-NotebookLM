# =============================================================================
# File: admin.py
# Module/Service: Observability Module (FR13 + FR14)
# Layer: Schema
# Purpose: Pydantic models for admin observability APIs (query-logs, cost-summary,
#          system health).
# Responsibilities:
#   - QueryLogResponse matching OpenAPI QueryLog
#   - CostSummaryResponse matching OpenAPI CostSummary (+ by_agent_type + tokens)
#   - SystemHealthResponse / HealthServiceItem matching OpenAPI SystemHealth
# Dependencies:
#   - Pydantic v2
# Public Exports:
#   - QueryLogResponse
#   - CostSummaryResponse, CostByModelItem, CostByRouteTypeItem, AgentTypeCostSummary
#   - SystemHealthResponse, HealthServiceItem, HealthStatusLiteral
# Database/Table: N/A
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml QueryLog, CostSummary,
#   SystemHealth
# Important Notes: by_agent_type + token totals are additive; health messages must
#   never include secrets or connection strings.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QueryLogResponse(BaseModel):
    """OpenAPI QueryLog — admin audit row (no workspace_id in schema)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    message_id: uuid.UUID | None = None
    cache_id: uuid.UUID | None = None
    query_text: str
    route_type: Literal[
        "cache_hit", "metadata", "section_extraction", "factoid", "complex"
    ]
    llm_calls_count: int
    model_used: str | None = None
    latency_ms: int | None = None
    created_at: datetime


class CostByModelItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_used: str
    calls: int
    cost_usd: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class CostByRouteTypeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_type: str
    count: int


class AgentTypeCostSummary(BaseModel):
    """Per Micro Agent cost/latency rollup (FR14)."""

    model_config = ConfigDict(extra="forbid")

    total_cost_usd: float = 0.0
    total_latency_ms: int = 0
    count: int = 0
    average_latency_ms: float = 0.0


class CostSummaryResponse(BaseModel):
    """OpenAPI CostSummary — cost/calls + additive token + by_agent_type."""

    model_config = ConfigDict(extra="forbid")

    total_cost_usd: float
    total_llm_calls: int
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    by_model: list[CostByModelItem] = Field(default_factory=list)
    by_route_type: list[CostByRouteTypeItem] = Field(default_factory=list)
    by_agent_type: dict[str, AgentTypeCostSummary] = Field(default_factory=dict)


HealthStatusLiteral = Literal["healthy", "degraded", "unhealthy", "unknown"]
HealthCategoryLiteral = Literal["core", "ai_retrieval"]


class HealthServiceItem(BaseModel):
    """OpenAPI HealthService — one dependency probe result."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    category: HealthCategoryLiteral
    status: HealthStatusLiteral
    provider: str | None = None
    message: str | None = None
    checked_at: datetime
    response_time_ms: int | None = None
    critical: bool = False


class SystemHealthResponse(BaseModel):
    """OpenAPI SystemHealth — overall + per-service availability."""

    model_config = ConfigDict(extra="forbid")

    status: HealthStatusLiteral
    checked_at: datetime
    message: str | None = None
    services: list[HealthServiceItem] = Field(default_factory=list)
