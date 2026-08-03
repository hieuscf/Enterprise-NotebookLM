# =============================================================================
# File: graph_agent.py
# Module/Service: Graph Agent (FR14)
# Layer: Service
# Purpose: Rule-based Knowledge Graph expansion for multi-hop queries (0 LLM).
# Responsibilities:
#   - Seed entities from rerank hits / Neo4j name match
#   - Expand 1–2 hops via RELATES_TO; collect related document ids
# Dependencies:
#   - Neo4jGraphAdapter, Settings, AgentEventData
# Public Exports:
#   - GraphAgent, GraphAgentResult, GraphExpansionPort
# Database/Table: N/A (Neo4j mirror; Part 4 writes agent_events)
# Related Modules: event_policy_engine, HybridRetrievalService (Second Retrieval)
# Important Notes: model_used=NULL, cost_usd=0. Neo4j timeout → empty expansion.
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.adapters.neo4j_graph import Neo4jGraphAdapter
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enums import AgentTriggerReason, AgentType
from app.services.event_policy.models import AgentEventData
from app.services.retrieval.confidence_engine import RerankedItem

logger = get_logger(__name__)


class GraphExpansionPort(Protocol):
    """Minimal Neo4j surface used by Graph Agent (testable without driver)."""

    def search_entities_with_chunks(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]: ...

    def expand_related_entities(
        self,
        *,
        workspace_id: UUID,
        seed_entity_ids: list[str],
        max_hops: int = 2,
    ) -> list[dict[str, Any]]: ...


class GraphAgentResult(BaseModel):
    """Graph expansion output for Second Retrieval context enrichment."""

    model_config = ConfigDict(frozen=True)

    expanded_entity_ids: list[str] = Field(default_factory=list)
    expanded_document_ids: list[str] = Field(default_factory=list)
    hops: int = Field(ge=0)
    event: AgentEventData


class GraphAgent:
    """Rule-based Graph Agent — expands entities, never answers the question."""

    def __init__(
        self,
        settings: Settings,
        graph: GraphExpansionPort | Neo4jGraphAdapter,
    ) -> None:
        self._settings = settings
        self._graph = graph

    def run(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        trigger_reason: AgentTriggerReason = AgentTriggerReason.multi_hop_reasoning,
        reranked_results: Sequence[RerankedItem | dict[str, object]] | None = None,
        seed_entity_ids: Sequence[str] | None = None,
        confidence_score: float | None = None,
    ) -> GraphAgentResult:
        """Expand related entities/documents up to configured hop depth."""
        started = time.perf_counter()
        hops = max(1, min(2, int(self._settings.graph_agent_max_hops)))
        items = [
            item if isinstance(item, RerankedItem) else RerankedItem.model_validate(item)
            for item in (reranked_results or [])
        ]
        seeds = _collect_seeds(
            graph=self._graph,
            workspace_id=workspace_id,
            query_text=query_text,
            items=items,
            seed_entity_ids=seed_entity_ids,
        )
        input_payload: dict[str, Any] = {
            "entities": seeds,
            "depth": hops,
            "query_text": (query_text or "")[:200],
        }

        try:
            rows = self._graph.expand_related_entities(
                workspace_id=workspace_id,
                seed_entity_ids=seeds,
                max_hops=hops,
            )
            entity_ids = sorted(
                {
                    str(row["entity_id"])
                    for row in rows
                    if row.get("entity_id") and str(row["entity_id"]) not in seeds
                }
            )
            document_ids = sorted(
                {
                    str(row["document_id"])
                    for row in rows
                    if row.get("document_id")
                }
            )
            # Also keep documents already linked on seed mentions via search.
            for item in items:
                if item.document_id:
                    document_ids.append(str(item.document_id))
            document_ids = sorted(set(document_ids))

            latency_ms = _elapsed_ms(started)
            output_payload = {
                "expanded_entity_ids": entity_ids,
                "expanded_document_ids": document_ids,
                "hops": hops,
            }
            event = _event(
                trigger_reason=trigger_reason,
                latency_ms=latency_ms,
                input_payload=input_payload,
                output_payload=output_payload,
                confidence_score=confidence_score,
                success=True,
                error=None,
            )
            _log_agent(event)
            return GraphAgentResult(
                expanded_entity_ids=entity_ids,
                expanded_document_ids=document_ids,
                hops=hops,
                event=event,
            )
        except Exception as exc:  # noqa: BLE001 — Neo4j timeout / driver errors
            latency_ms = _elapsed_ms(started)
            logger.warning("graph_agent_failed", error=str(exc))
            output_payload = {
                "expanded_entity_ids": [],
                "expanded_document_ids": [],
                "hops": hops,
            }
            event = _event(
                trigger_reason=trigger_reason,
                latency_ms=latency_ms,
                input_payload=input_payload,
                output_payload=output_payload,
                confidence_score=confidence_score,
                success=False,
                error=type(exc).__name__,
            )
            _log_agent(event)
            return GraphAgentResult(
                expanded_entity_ids=[],
                expanded_document_ids=[],
                hops=hops,
                event=event,
            )


def _collect_seeds(
    *,
    graph: GraphExpansionPort,
    workspace_id: UUID,
    query_text: str,
    items: list[RerankedItem],
    seed_entity_ids: Sequence[str] | None,
) -> list[str]:
    seeds: list[str] = []
    if seed_entity_ids:
        seeds.extend(str(eid) for eid in seed_entity_ids if eid)
    for item in items:
        if item.entity_id:
            seeds.append(str(item.entity_id))
    seeds = list(dict.fromkeys(seeds))  # stable unique
    if seeds:
        return seeds[:20]

    # Fallback: name/alias match against Neo4j (no re-embedding).
    try:
        rows = graph.search_entities_with_chunks(
            workspace_id=workspace_id,
            query_text=query_text or "",
            top_k=10,
        )
    except Exception:  # noqa: BLE001
        return []
    return list(
        dict.fromkeys(str(r["entity_id"]) for r in rows if r.get("entity_id"))
    )[:20]


def _event(
    *,
    trigger_reason: AgentTriggerReason,
    latency_ms: int,
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    confidence_score: float | None,
    success: bool,
    error: str | None,
) -> AgentEventData:
    return AgentEventData(
        agent_type=AgentType.graph,
        trigger_reason=trigger_reason,
        model_used=None,
        cost_usd=Decimal("0"),
        latency_ms=latency_ms,
        input_payload=input_payload,
        output_payload=output_payload,
        confidence_score=confidence_score,
        triggered_second_retrieval=True,
        skip_second_retrieval=False,
        success=success,
        error=error,
    )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _log_agent(event: AgentEventData) -> None:
    logger.info(
        "agent_run",
        agent_type=event.agent_type.value,
        trigger_reason=event.trigger_reason.value,
        latency_ms=event.latency_ms,
        cost_usd=str(event.cost_usd),
        success=event.success,
    )
