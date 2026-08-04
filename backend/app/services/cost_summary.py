# =============================================================================
# File: cost_summary.py
# Module/Service: Observability Module (FR13 + FR14)
# Layer: Service
# Purpose: Build CostSummary response (message_generations + agent_events).
# Responsibilities:
#   - Aggregate totals / by_model / by_route_type (existing contract)
#   - Add by_agent_type from agent_events (backward-compatible extension)
# Dependencies:
#   - CostSummaryRepository, CostSummary schemas
# Public Exports:
#   - CostSummaryService
# Database/Table: message_generations, agent_events
# Related Modules: app.api.admin, OpenAPI CostSummary
# Important Notes: Does not mutate generation totals with agent costs.
# =============================================================================

from __future__ import annotations

import uuid
from datetime import date

from app.repositories.cost_summary import CostSummaryRepository
from app.schemas.admin import (
    AgentTypeCostSummary,
    CostByModelItem,
    CostByRouteTypeItem,
    CostSummaryResponse,
)


class CostSummaryService:
    """Admin cost analytics for a workspace."""

    def __init__(self, repo: CostSummaryRepository) -> None:
        self._repo = repo

    async def get_summary(
        self,
        *,
        workspace_id: uuid.UUID,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> CostSummaryResponse:
        total_cost, total_calls, by_model, by_route = await self._repo.summarize_generations(
            workspace_id=workspace_id,
            date_from=date_from,
            date_to=date_to,
        )
        by_agent = await self._repo.summarize_agents(
            workspace_id=workspace_id,
            date_from=date_from,
            date_to=date_to,
        )
        return CostSummaryResponse(
            total_cost_usd=float(total_cost),
            total_llm_calls=total_calls,
            by_model=[
                CostByModelItem(
                    model_used=m.model_used,
                    calls=m.calls,
                    cost_usd=float(m.cost_usd),
                )
                for m in by_model
            ],
            by_route_type=[
                CostByRouteTypeItem(route_type=r.route_type, count=r.count)
                for r in by_route
            ],
            by_agent_type={
                agent: AgentTypeCostSummary(
                    total_cost_usd=float(agg.total_cost_usd),
                    total_latency_ms=agg.total_latency_ms,
                    count=agg.count,
                    average_latency_ms=agg.average_latency_ms,
                )
                for agent, agg in by_agent.items()
            },
        )
