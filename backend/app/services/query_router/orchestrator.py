# =============================================================================
# File: orchestrator.py
# Module/Service: Query Router Execution / Query Orchestrator
# Layer: Service
# Purpose: Sole internal API for Chat Service — route then execute 0-LLM branches.
# Responsibilities:
#   - handle_query → QueryRouter.route → branch switch → unified log_query_routing
#   - cache_hit / metadata / factoid (0 LLM); complex → ComplexQueryPipeline (FR14)
# Dependencies:
#   - QueryRouter, MetadataBranch, FactoidBranch, logging_service, ComplexQueryPipeline
# Public Exports:
#   - QueryOrchestrator, COMPLEX_STATUS
# Database/Table: query_logs (via logging_service); FR14 tables via ComplexQueryPipeline
# Related Modules: Chat Service (downstream writes message_generations);
#   ComplexQueryPipeline (FR14) when injected for complex route
# Important Notes:
#   - Prompt Construction / answer LLM live in ComplexQueryPipeline (optional port).
#   - Never return before log_query_routing completes (best-effort).
#   - Do not call QueryRouter elsewhere from Chat — use handle_query only.
#   - cache_hit / metadata / factoid unchanged (0 LLM); complex only runs FR14.
# =============================================================================

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.core.logging import get_logger
from app.models.enums import RouteType
from app.services.query_router.factoid_branch import FactoidBranch
from app.services.query_router.interfaces.query_log_repository import QueryLogRepository
from app.services.query_router.logging_models import QueryRoutingLogContext
from app.services.query_router.logging_service import QueryRoutingLogger
from app.services.query_router.metadata_branch import MetadataBranch
from app.services.query_router.router import QueryRouter
from app.services.query_router.schemas import (
    CacheEntryView,
    CitationRef,
    QueryExecutionResult,
)

if TYPE_CHECKING:
    from app.services.chat.complex_query_pipeline import ComplexQueryPipeline

logger = get_logger(__name__)

COMPLEX_STATUS = "pending_llm_pipeline"


class QueryOrchestrator:
    """Execute routed queries for Chat Service (0-LLM branches + FR14 complex)."""

    def __init__(
        self,
        *,
        router: QueryRouter,
        metadata_branch: MetadataBranch,
        factoid_branch: FactoidBranch,
        query_log_repository: QueryLogRepository,
        session_id: UUID | None = None,
        complex_pipeline: ComplexQueryPipeline | None = None,
    ) -> None:
        self._router = router
        self._metadata = metadata_branch
        self._factoid = factoid_branch
        self._logger = QueryRoutingLogger(query_log_repository)
        self._session_id = session_id
        self._complex_pipeline = complex_pipeline

    async def handle_query(
        self,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
        *,
        message_id: UUID | None = None,
        session_id: UUID | None = None,
        llm_calls_count: int | None = None,
        model_used: str | None = None,
        assistant_message_id: UUID | None = None,
        chat_history: list[Any] | None = None,
    ) -> QueryExecutionResult:
        """Route and execute a user query; always attempt unified query_logs write.

        Args:
            workspace_id: Tenant scope (caller must enforce RBAC).
            user_id: Authenticated user.
            query_text: Raw user question.
            message_id: Optional user ``chat_messages.id`` for retrievals/agent_events.
            session_id: Optional chat session id (correlation only; not a column).
            llm_calls_count: Override when Complex pipeline is not injected.
            model_used: Override when Complex pipeline is not injected.
            assistant_message_id: Optional assistant message for message_generations.
            chat_history: Optional prior turns for Rewrite Agent.

        Returns:
            Unified ``QueryExecutionResult`` including logging metadata for Chat.
        """
        # Monotonic clock — Query Router wall time (not wall-clock datetime).
        started = time.perf_counter()
        decision = await self._router.route(workspace_id, user_id, query_text)

        answer: str | None = None
        citation_refs: list[CitationRef] = []
        metadata: dict[str, Any] = {}
        verify = False
        status: str | None = None
        cache_id: UUID | None = None
        final_route = decision.route_type
        effective_llm_calls = 0
        effective_model: str | None = None
        message_generation_id: UUID | None = None

        if decision.route_type == RouteType.cache_hit:
            answer, citation_refs, metadata, verify, cache_id = _from_cache(
                decision.cache_entry
            )
            final_route = RouteType.cache_hit
            effective_llm_calls = 0
            effective_model = None

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
            effective_llm_calls = 0
            effective_model = None

        elif decision.route_type == RouteType.factoid:
            branch = await self._factoid.execute(
                workspace_id=workspace_id,
                decision=decision,
                query_text=query_text,
            )
            final_route = branch.route_type
            answer = branch.answer
            citation_refs = branch.citation_refs
            metadata = branch.metadata
            verify = branch.verify
            status = branch.status
            effective_llm_calls = 0
            effective_model = None

        else:
            # complex — FR14 Confidence Engine + Event Policy + Agents when wired
            final_route = RouteType.complex
            if self._complex_pipeline is not None and message_id is not None:
                pipeline_result = await self._complex_pipeline.run(
                    workspace_id=workspace_id,
                    query_text=query_text,
                    message_id=message_id,
                    initial_retrieval=decision.retrieval_result,
                    assistant_message_id=assistant_message_id,
                    chat_history=chat_history,
                )
                answer = pipeline_result.answer
                citation_refs = pipeline_result.citation_refs
                metadata = {
                    **pipeline_result.metadata,
                    "confidence_level": (
                        pipeline_result.confidence_level.value
                        if pipeline_result.confidence_level
                        else None
                    ),
                    "confidence_score": pipeline_result.confidence_score,
                    "agent_triggered": pipeline_result.agent_triggered,
                    "retrieval_pass_final": pipeline_result.retrieval_pass_final,
                }
                verify = pipeline_result.verify
                status = pipeline_result.status
                # Includes Rewrite lightweight call (exception) + main answer LLM.
                effective_llm_calls = int(pipeline_result.llm_calls_count)
                effective_model = pipeline_result.model_used
                message_generation_id = pipeline_result.message_generation_id
            else:
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
                effective_llm_calls = (
                    int(llm_calls_count) if llm_calls_count is not None else 0
                )
                effective_model = model_used

        # If metadata/factoid downgraded to complex, keep 0-LLM until Complex runs.
        if final_route in {RouteType.metadata, RouteType.factoid, RouteType.cache_hit}:
            effective_llm_calls = 0
            effective_model = None
            if final_route != RouteType.cache_hit:
                cache_id = None

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))

        log_result = await self._logger.log_query_routing(
            QueryRoutingLogContext(
                workspace_id=workspace_id,
                user_id=user_id,
                query_text=query_text,
                route_type=final_route,
                latency_ms=latency_ms,
                llm_calls_count=effective_llm_calls,
                cache_id=cache_id,
                message_id=message_id,
                model_used=effective_model,
                session_id=session_id or self._session_id,
            )
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
            llm_calls_count=effective_llm_calls,
            model_used=effective_model,
            query_log_id=log_result.query_log_id,
            message_generation_id=message_generation_id,
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
