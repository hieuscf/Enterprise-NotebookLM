# =============================================================================
# File: orchestrator.py
# Module/Service: Query Router Execution / Query Orchestrator
# Layer: Service
# Purpose: Sole internal API for Chat Service — execute the FR11 branch.
# Responsibilities:
#   - handle_query → QueryRouter.route → cache / metadata / section /
#     factoid / complex
#   - Metadata/section/factoid miss or low-confidence → ComplexQueryPipeline fallback
#   - Write-back verified factoid/complex answers to query_cache
#   - Persist extractive retrievals + verify citations (0 LLM, chunk_id lookup)
# Dependencies:
#   - QueryRouter, MetadataBranch, FactoidBranch, logging_service,
#     ComplexQueryPipeline, QueryCacheService, CitationVerificationService
# Public Exports:
#   - QueryOrchestrator, COMPLEX_STATUS
# Database/Table: query_logs (via logging_service); query_cache write-back;
#   retrievals (extractive provenance); FR14 tables via ComplexQueryPipeline
# Related Modules: Chat Service (downstream writes message_generations)
# Important Notes:
#   - 0-LLM branches: cache_hit / metadata / section_extraction / factoid.
#   - 0 LLM does not mean 0 citations — section_extraction writes retrievals.
#   - Never return before log_query_routing completes (best-effort).
#   - Do not call QueryRouter elsewhere from Chat — use handle_query only.
#   - Cache write-back is best-effort and never blocks the answer.
# =============================================================================

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enums import RouteType
from app.services.query_router.cache import QueryCacheService, citation_refs_from_stored
from app.services.query_router.factoid_branch import FactoidBranch
from app.services.query_router.interfaces.query_log_repository import QueryLogRepository
from app.services.query_router.logging_models import QueryRoutingLogContext
from app.services.query_router.logging_service import QueryRoutingLogger
from app.services.query_router.metadata_branch import MetadataBranch
from app.services.query_router.router import QueryRouter
from app.services.query_router.schemas import CitationRef, QueryExecutionResult, RouteDecision
from app.services.query_router.section_branch import SectionExtractionBranch

if TYPE_CHECKING:
    from app.repositories.retrieval_records import RetrievalRecordRepository
    from app.services.chat.complex_query_pipeline import ComplexQueryPipeline
    from app.services.citation_verification.service import CitationVerificationService

logger = get_logger(__name__)

COMPLEX_STATUS = "pending_llm_pipeline"
_CACHEABLE_COMPLEX_STATUSES = frozenset({"completed", "sql_agent_direct"})


class QueryOrchestrator:
    """Execute chat queries according to the Query Router decision (FR11)."""

    def __init__(
        self,
        *,
        router: QueryRouter,
        metadata_branch: MetadataBranch,
        factoid_branch: FactoidBranch,
        query_log_repository: QueryLogRepository,
        session_id: UUID | None = None,
        complex_pipeline: ComplexQueryPipeline | None = None,
        cache: QueryCacheService | None = None,
        settings: Settings | None = None,
        section_branch: SectionExtractionBranch | None = None,
        retrieval_records: RetrievalRecordRepository | None = None,
        citation_verifier: CitationVerificationService | None = None,
    ) -> None:
        self._router = router
        self._metadata = metadata_branch
        self._factoid = factoid_branch
        self._section = section_branch
        self._logger = QueryRoutingLogger(query_log_repository)
        self._session_id = session_id
        self._complex_pipeline = complex_pipeline
        self._cache = cache
        self._settings = settings
        self._retrieval_records = retrieval_records
        self._citation_verifier = citation_verifier

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
        """Route then execute; always attempt query_logs write.

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
        started = time.perf_counter()
        decision = await self._router.route(workspace_id, user_id, query_text)

        if decision.route_type is RouteType.cache_hit and decision.cache_entry is not None:
            result = self._from_cache(decision)
        elif decision.route_type is RouteType.metadata:
            result = await self._run_metadata(
                workspace_id=workspace_id,
                user_id=user_id,
                query_text=query_text,
                decision=decision,
                message_id=message_id,
                assistant_message_id=assistant_message_id,
                chat_history=chat_history,
                llm_calls_count=llm_calls_count,
                model_used=model_used,
            )
        elif decision.route_type is RouteType.section_extraction:
            result = await self._run_section(
                workspace_id=workspace_id,
                query_text=query_text,
                decision=decision,
                message_id=message_id,
                assistant_message_id=assistant_message_id,
                chat_history=chat_history,
                llm_calls_count=llm_calls_count,
                model_used=model_used,
            )
        elif decision.route_type is RouteType.factoid:
            result = await self._run_factoid(
                workspace_id=workspace_id,
                query_text=query_text,
                decision=decision,
                message_id=message_id,
                assistant_message_id=assistant_message_id,
                chat_history=chat_history,
                llm_calls_count=llm_calls_count,
                model_used=model_used,
            )
        else:
            result = await self._run_complex(
                workspace_id=workspace_id,
                query_text=query_text,
                decision=decision,
                message_id=message_id,
                assistant_message_id=assistant_message_id,
                chat_history=chat_history,
                llm_calls_count=llm_calls_count,
                model_used=model_used,
            )

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        result.latency_ms = latency_ms

        log_result = await self._logger.log_query_routing(
            QueryRoutingLogContext(
                workspace_id=workspace_id,
                user_id=user_id,
                query_text=query_text,
                route_type=result.route_type,
                latency_ms=latency_ms,
                llm_calls_count=result.llm_calls_count,
                cache_id=result.cache_id,
                message_id=message_id,
                model_used=result.model_used,
                session_id=session_id or self._session_id,
            )
        )
        result.query_log_id = log_result.query_log_id
        return result

    def _from_cache(self, decision: RouteDecision) -> QueryExecutionResult:
        entry = decision.cache_entry
        assert entry is not None
        refs = citation_refs_from_stored(entry.citation_refs)
        return QueryExecutionResult(
            route_type=RouteType.cache_hit,
            answer=entry.answer,
            citation_refs=refs,
            metadata={
                "cache_hit": True,
                "match_type": entry.match_type,
                "similarity": entry.similarity,
            },
            verify=True,
            latency_ms=0,
            status="completed",
            cache_id=entry.id,
            llm_calls_count=0,
            model_used=None,
        )

    async def _run_metadata(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
        decision: RouteDecision,
        message_id: UUID | None,
        assistant_message_id: UUID | None,
        chat_history: list[Any] | None,
        llm_calls_count: int | None,
        model_used: str | None,
    ) -> QueryExecutionResult:
        try:
            branch = await self._metadata.execute(
                workspace_id=workspace_id,
                user_id=user_id,
                query_text=query_text,
                decision=decision,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "metadata_branch_failed",
                workspace_id=str(workspace_id),
                error=type(exc).__name__,
            )
            branch = None
        if branch is not None and branch.route_type is RouteType.metadata:
            return self._from_zero_llm_branch(branch, route_type=RouteType.metadata)
        return await self._run_complex(
            workspace_id=workspace_id,
            query_text=query_text,
            decision=decision,
            message_id=message_id,
            assistant_message_id=assistant_message_id,
            chat_history=chat_history,
            llm_calls_count=llm_calls_count,
            model_used=model_used,
        )

    async def _run_section(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        decision: RouteDecision,
        message_id: UUID | None,
        assistant_message_id: UUID | None,
        chat_history: list[Any] | None,
        llm_calls_count: int | None,
        model_used: str | None,
    ) -> QueryExecutionResult:
        branch = None
        if self._section is not None:
            try:
                branch = await self._section.execute(
                    workspace_id=workspace_id,
                    query_text=query_text,
                    decision=decision,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "section_extraction_branch_failed",
                    workspace_id=str(workspace_id),
                    error=type(exc).__name__,
                )
                branch = None
        if (
            branch is not None
            and branch.route_type is RouteType.section_extraction
            and (branch.answer or "").strip()
        ):
            result = self._from_zero_llm_branch(
                branch, route_type=RouteType.section_extraction
            )
            result = await self._seal_extractive_provenance(
                workspace_id=workspace_id,
                message_id=message_id,
                result=result,
            )
            await self._maybe_write_cache(
                workspace_id=workspace_id,
                query_text=query_text,
                answer=result.answer,
                citation_refs=result.citation_refs,
                verify=result.verify,
            )
            return result
        return await self._run_complex(
            workspace_id=workspace_id,
            query_text=query_text,
            decision=decision,
            message_id=message_id,
            assistant_message_id=assistant_message_id,
            chat_history=chat_history,
            llm_calls_count=llm_calls_count,
            model_used=model_used,
        )

    async def _run_factoid(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        decision: RouteDecision,
        message_id: UUID | None,
        assistant_message_id: UUID | None,
        chat_history: list[Any] | None,
        llm_calls_count: int | None,
        model_used: str | None,
    ) -> QueryExecutionResult:
        try:
            branch = await self._factoid.execute(
                workspace_id=workspace_id,
                decision=decision,
                query_text=query_text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "factoid_branch_failed",
                workspace_id=str(workspace_id),
                error=type(exc).__name__,
            )
            branch = None
        if branch is not None and branch.route_type is RouteType.factoid:
            result = self._from_zero_llm_branch(branch, route_type=RouteType.factoid)
            await self._maybe_write_cache(
                workspace_id=workspace_id,
                query_text=query_text,
                answer=result.answer,
                citation_refs=result.citation_refs,
                verify=result.verify,
            )
            return result
        return await self._run_complex(
            workspace_id=workspace_id,
            query_text=query_text,
            decision=decision,
            message_id=message_id,
            assistant_message_id=assistant_message_id,
            chat_history=chat_history,
            llm_calls_count=llm_calls_count,
            model_used=model_used,
        )

    async def _run_complex(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        decision: RouteDecision,
        message_id: UUID | None,
        assistant_message_id: UUID | None,
        chat_history: list[Any] | None,
        llm_calls_count: int | None,
        model_used: str | None,
    ) -> QueryExecutionResult:
        if self._complex_pipeline is not None and message_id is not None:
            pipeline_result = await self._complex_pipeline.run(
                workspace_id=workspace_id,
                query_text=query_text,
                message_id=message_id,
                initial_retrieval=decision.retrieval_result,
                assistant_message_id=assistant_message_id,
                chat_history=chat_history,
            )
            result = QueryExecutionResult(
                route_type=RouteType.complex,
                answer=pipeline_result.answer,
                citation_refs=pipeline_result.citation_refs,
                metadata={
                    **pipeline_result.metadata,
                    "confidence_level": (
                        pipeline_result.confidence_level.value
                        if pipeline_result.confidence_level
                        else None
                    ),
                    "confidence_score": pipeline_result.confidence_score,
                    "agent_triggered": pipeline_result.agent_triggered,
                    "retrieval_pass_final": pipeline_result.retrieval_pass_final,
                },
                verify=pipeline_result.verify,
                latency_ms=0,
                status=pipeline_result.status,
                cache_id=None,
                llm_calls_count=int(pipeline_result.llm_calls_count),
                model_used=pipeline_result.model_used,
                message_generation_id=pipeline_result.message_generation_id,
            )
            if (
                result.verify
                and (result.answer or "").strip()
                and result.status in _CACHEABLE_COMPLEX_STATUSES
            ):
                await self._maybe_write_cache(
                    workspace_id=workspace_id,
                    query_text=query_text,
                    answer=result.answer,
                    citation_refs=result.citation_refs,
                    verify=result.verify,
                )
            return result

        metadata: dict[str, Any] = {
            "route_type": RouteType.complex.value,
            "status": COMPLEX_STATUS,
        }
        if decision.retrieval_result is not None:
            metadata["retrieval_item_count"] = len(decision.retrieval_result.items)
        return QueryExecutionResult(
            route_type=RouteType.complex,
            answer=None,
            citation_refs=[],
            metadata=metadata,
            verify=False,
            latency_ms=0,
            status=COMPLEX_STATUS,
            cache_id=None,
            llm_calls_count=int(llm_calls_count) if llm_calls_count is not None else 0,
            model_used=model_used,
            message_generation_id=None,
        )

    async def _seal_extractive_provenance(
        self,
        *,
        workspace_id: UUID,
        message_id: UUID | None,
        result: QueryExecutionResult,
    ) -> QueryExecutionResult:
        """Write retrievals + extractive-verify citations (page_number optional)."""
        refs = list(result.citation_refs)
        if not refs:
            return result

        from app.services.citation_verification.extractive import (
            merge_extractive_evidence,
            provenance_candidates_from_refs,
        )
        from app.services.citation_verification.service import (
            CitationVerificationService,
            evidence_from_candidates,
        )

        candidates = provenance_candidates_from_refs(
            workspace_id=workspace_id, refs=refs
        )
        evidence_message_id = message_id or uuid4()
        if self._retrieval_records is not None and message_id is not None:
            try:
                await self._retrieval_records.insert_candidates(
                    message_id=message_id,
                    candidates=candidates,
                    retrieval_pass=1,
                )
            except Exception as exc:  # noqa: BLE001 — never block the extractive answer
                logger.warning(
                    "section_extraction_retrievals_persist_failed",
                    workspace_id=str(workspace_id),
                    error=type(exc).__name__,
                )

        evidence = evidence_from_candidates(
            workspace_id=workspace_id,
            message_id=evidence_message_id,
            candidates=candidates,
            use_candidate_workspace=True,
        )
        if self._retrieval_records is not None and message_id is not None:
            try:
                persisted = await self._retrieval_records.list_integrity_for_cited_chunks(
                    message_id=message_id,
                    chunk_ids=[ref.chunk_id for ref in refs if ref.chunk_id is not None],
                )
                if persisted:
                    evidence = merge_extractive_evidence(
                        retrieved=evidence,
                        persisted=persisted,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "section_extraction_integrity_lookup_failed",
                    workspace_id=str(workspace_id),
                    error=type(exc).__name__,
                )

        verifier = self._citation_verifier or CitationVerificationService()
        report = verifier.verify_extractive_citations(
            workspace_id=workspace_id,
            message_id=evidence_message_id,
            refs=refs,
            evidence=evidence,
        )
        verified_refs = verifier.to_citation_refs(report)
        result.citation_refs = verified_refs
        result.verify = bool(verified_refs)
        result.metadata = {
            **dict(result.metadata or {}),
            "answer_type": "extractive",
            "citation_verified_count": report.valid_count,
            "citation_invalid_count": report.invalid_count,
        }
        return result

    def _from_zero_llm_branch(
        self,
        branch: Any,
        *,
        route_type: RouteType,
    ) -> QueryExecutionResult:
        refs = list(getattr(branch, "citation_refs", None) or [])
        meta = dict(getattr(branch, "metadata", None) or {})
        status = getattr(branch, "status", None) or "completed"
        return QueryExecutionResult(
            route_type=route_type,
            answer=getattr(branch, "answer", None),
            citation_refs=refs,
            metadata=meta,
            verify=bool(getattr(branch, "verify", False)),
            latency_ms=0,
            status=status,
            cache_id=None,
            llm_calls_count=0,
            model_used=None,
        )

    async def _maybe_write_cache(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        answer: str | None,
        citation_refs: list[CitationRef],
        verify: bool,
    ) -> None:
        if self._cache is None or not verify or not (answer or "").strip():
            return
        ttl = 86_400
        if self._settings is not None:
            ttl = int(self._settings.query_cache_default_ttl_seconds)
        if ttl <= 0:
            return
        try:
            await self._cache.save_query_cache(
                workspace_id=workspace_id,
                query_text=query_text,
                answer=answer or "",
                citation_refs=citation_refs,
                ttl_seconds=ttl,
            )
        except Exception as exc:  # noqa: BLE001 — never block the user answer
            logger.warning(
                "query_cache_writeback_failed",
                workspace_id=str(workspace_id),
                error=type(exc).__name__,
            )
