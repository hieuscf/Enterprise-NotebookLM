# =============================================================================
# File: orchestrator.py
# Module/Service: Query Router Execution / Query Orchestrator
# Layer: Service
# Purpose: Sole internal API for Chat Service — route then execute 0-LLM branches.
# Responsibilities:
#   - handle_query → QueryRouter.route → branch switch → unified logging
#   - cache_hit / metadata / factoid execution; complex placeholder only
# Dependencies:
#   - QueryRouter, MetadataBranch, FactoidBranch, log_route_decision
# Public Exports:
#   - QueryOrchestrator, COMPLEX_STATUS
# Database/Table: query_logs, message_generations (via logging)
# Related Modules: Chat Service (downstream), Query Router (Part 3)
# Important Notes:
#   - No Prompt Construction / LLM in this module.
#   - Never return before log_route_decision.
#   - Do not call QueryRouter elsewhere from Chat — use handle_query only.
# =============================================================================

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.models.enums import RouteType
from app.repositories.query_logs import QueryObservabilityRepository
from app.services.query_router.factoid_branch import FactoidBranch
from app.services.query_router.logging import log_route_decision
from app.services.query_router.metadata_branch import MetadataBranch
from app.services.query_router.router import QueryRouter
from app.services.query_router.schemas import (
    CacheEntryView,
    CitationRef,
    QueryExecutionResult,
)

logger = get_logger(__name__)

COMPLEX_STATUS = "pending_llm_pipeline"


class QueryOrchestrator:
    """Execute routed queries for Chat Service (0-LLM branches + complex stub)."""

    def __init__(
        self,
        *,
        router: QueryRouter,
        metadata_branch: MetadataBranch,
        factoid_branch: FactoidBranch,
        observability: QueryObservabilityRepository,
    ) -> None:
        self._router = router
        self._metadata = metadata_branch
        self._factoid = factoid_branch
        self._observability = observability

    async def handle_query(
        self,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
        *,
        message_id: UUID | None = None,
    ) -> QueryExecutionResult:
        """Route and execute a user query; always persist observability rows.

        Args:
            workspace_id: Tenant scope (caller must enforce RBAC).
            user_id: Authenticated user.
            query_text: Raw user question.
            message_id: Optional assistant ``chat_messages.id`` so
                ``message_generations`` can be written (FK required). Chat
                Service should pass this when available.

        Returns:
            Unified ``QueryExecutionResult`` independent of branch.
        """
        started = time.perf_counter()
        decision = await self._router.route(workspace_id, user_id, query_text)

        answer: str | None = None
        citation_refs: list[CitationRef] = []
        metadata: dict[str, Any] = {}
        verify = False
        status: str | None = None
        cache_id: UUID | None = None
        final_route = decision.route_type

        if decision.route_type == RouteType.cache_hit:
            answer, citation_refs, metadata, verify, cache_id = _from_cache(
                decision.cache_entry
            )
            final_route = RouteType.cache_hit

        elif decision.route_type == RouteType.metadata:
            branch = await self._metadata.execute(
                workspace_id=workspace_id,
                user_id=user_id,
                query_text=query_text,
                decision=decision,
            )
            final_route = branch.route_type
            answer = branch.answer
            citation_refs = branch.citation_refs
            metadata = branch.metadata
            verify = branch.verify
            status = branch.status

        elif decision.route_type == RouteType.factoid:
            branch = await self._factoid.execute(
                workspace_id=workspace_id,
                decision=decision,
            )
            final_route = branch.route_type
            answer = branch.answer
            citation_refs = branch.citation_refs
            metadata = branch.metadata
            verify = branch.verify
            status = branch.status

        else:
            # complex — placeholder only (Chat Service attaches LLM later)
            final_route = RouteType.complex
            answer = None
            citation_refs = []
            metadata = {
                "route_type": RouteType.complex.value,
                "status": COMPLEX_STATUS,
            }
            if decision.retrieval_result is not None:
                metadata["retrieval_item_count"] = len(decision.retrieval_result.items)
            verify = False
            status = COMPLEX_STATUS

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))

        log_result = await log_route_decision(
            observability=self._observability,
            workspace_id=workspace_id,
            user_id=user_id,
            query_text=query_text,
            route_type=final_route,
            message_id=message_id,
            cache_id=cache_id,
            latency_ms=latency_ms,
            llm_calls_count=0,
            model_used=None,
        )

        return QueryExecutionResult(
            route_type=final_route,
            answer=answer,
            citation_refs=citation_refs,
            metadata=metadata,
            verify=verify,
            latency_ms=latency_ms,
            status=status,
            cache_id=cache_id,
            query_log_id=log_result.query_log_id,
            message_generation_id=log_result.message_generation_id,
        )


def _from_cache(
    entry: CacheEntryView | None,
) -> tuple[str | None, list[CitationRef], dict[str, Any], bool, UUID | None]:
    """Materialize cache_hit payload without Retrieval / Metadata / Factoid / LLM."""
    if entry is None:
        logger.warning("cache_hit_without_entry")
        return None, [], {}, False, None
    citations = _parse_cached_citations(entry.citation_refs)
    return (
        entry.answer,
        citations,
        {"cache_match": entry.match_type, "query_hash": entry.query_hash},
        True,
        entry.id,
    )


def _parse_cached_citations(
    raw: dict[str, Any] | list[Any] | None,
) -> list[CitationRef]:
    if raw is None:
        return []
    items: list[Any]
    if isinstance(raw, dict):
        maybe = raw.get("items") or raw.get("citations") or raw.get("citation_refs")
        if isinstance(maybe, list):
            items = maybe
        elif {"chunk_id", "document_id"} & set(raw.keys()):
            items = [raw]
        else:
            return []
    elif isinstance(raw, list):
        items = raw
    else:
        return []

    out: list[CitationRef] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        chunk_raw = item.get("chunk_id")
        doc_raw = item.get("document_id")
        page_raw = item.get("page_number")
        try:
            chunk_id = UUID(str(chunk_raw)) if chunk_raw else None
            document_id = UUID(str(doc_raw)) if doc_raw else None
        except (TypeError, ValueError):
            continue
        page_number: int | None
        try:
            page_number = int(page_raw) if page_raw is not None else None
        except (TypeError, ValueError):
            page_number = None
        out.append(
            CitationRef(
                chunk_id=chunk_id,
                document_id=document_id,
                page_number=page_number,
                verify=bool(item.get("verify", True)),
            )
        )
    return out
