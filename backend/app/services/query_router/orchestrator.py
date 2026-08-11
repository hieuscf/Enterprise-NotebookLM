# =============================================================================
# File: orchestrator.py
# Module/Service: Query Router Execution / Query Orchestrator
# Layer: Service
# Purpose: Sole internal API for Chat Service — always execute complex directly.
# Responsibilities:
#   - handle_query → QueryRouter.route (always complex) → ComplexQueryPipeline
# Dependencies:
#   - QueryRouter, MetadataBranch, FactoidBranch, logging_service, ComplexQueryPipeline
# Public Exports:
#   - QueryOrchestrator, COMPLEX_STATUS
# Database/Table: query_logs (via logging_service); FR14 tables via ComplexQueryPipeline
# Related Modules: Chat Service (downstream writes message_generations);
#   ComplexQueryPipeline (FR14) — mandatory for every chat query
# Important Notes:
#   - Mandatory product rule: every chat query executes complex directly —
#     no cache check, no metadata / factoid short-circuit.
#   - Metadata / factoid branches are retained for DI/compat but not executed.
#   - Never return before log_query_routing completes (best-effort).
#   - Do not call QueryRouter elsewhere from Chat — use handle_query only.
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
from app.services.query_router.schemas import QueryExecutionResult

if TYPE_CHECKING:
    from app.services.chat.complex_query_pipeline import ComplexQueryPipeline

logger = get_logger(__name__)

COMPLEX_STATUS = "pending_llm_pipeline"


class QueryOrchestrator:
    """Execute chat queries: always run ComplexQueryPipeline directly."""

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
        """Always execute complex directly; always attempt query_logs write.

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
            ``route_type`` is always ``complex``; no cache is ever consulted.
        """
        # Monotonic clock — Query Router wall time (not wall-clock datetime).
        started = time.perf_counter()
        decision = await self._router.route(workspace_id, user_id, query_text)

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
            message_generation_id = None

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))

        log_result = await self._logger.log_query_routing(
            QueryRoutingLogContext(
                workspace_id=workspace_id,
                user_id=user_id,
                query_text=query_text,
                route_type=final_route,
                latency_ms=latency_ms,
                llm_calls_count=effective_llm_calls,
                cache_id=None,
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
            cache_id=None,
            llm_calls_count=effective_llm_calls,
            model_used=effective_model,
            query_log_id=log_result.query_log_id,
            message_generation_id=message_generation_id,
        )
