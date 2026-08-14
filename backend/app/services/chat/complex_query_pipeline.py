# =============================================================================
# File: complex_query_pipeline.py
# Module/Service: Chat Service / Complex Query Pipeline (FR14)
# Layer: Service
# Purpose: Integrate Confidence Engine + Event Policy + Micro Agents into complex.
# Responsibilities:
#   - Post-rerank confidence; High → Prompt/LLM; Low → agent (+ optional pass=2)
#   - Persist retrievals / agent_events / message_generations confidence fields
#   - Enforce one-agent + one-Second-Retrieval limit (no loops)
#   - Run Citation Verification (FR5) after the answer LLM — deterministic, no LLM
# Dependencies:
#   - HybridRetrievalService, confidence_engine, event_policy, agents, repos
#   - CitationVerificationService
# Public Exports:
#   - ComplexQueryPipeline, ComplexPipelineResult, AnswerGeneratorPort
# Database/Table: retrievals, agent_events, message_generations, citations
# Related Modules: QueryOrchestrator (complex branch), Prompt Construction,
#   Citation Verification Layer
# Important Notes:
#   - Only for route_type=complex. Does not alter Query Router classification.
#   - Rewrite Agent Haiku is the sole lightweight-model exception (not answer LLM).
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.core.config import Settings
from app.core.fr14_metrics import get_fr14_metrics
from app.core.logging import get_logger
from app.models.enums import AgentType, ConfidenceLevel, RouteType
from app.repositories.agent_events import AgentEventRepository
from app.repositories.query_logs import QueryObservabilityRepository
from app.repositories.retrieval_records import RetrievalRecordRepository
from app.services.chat.answer_sanitizer import rewrite_inline_citation_markers
from app.services.citation_verification.service import (
    INSUFFICIENT_EVIDENCE_ANSWER,
    CitationVerificationService,
    evidence_from_candidates,
    merge_retrieved_and_persisted_evidence,
)
from app.services.event_policy.agents.graph_agent import GraphAgent
from app.services.event_policy.agents.rewrite_agent import RewriteAgent
from app.services.event_policy.agents.sql_agent import SqlAgent
from app.services.event_policy.event_policy_engine import decide_agent
from app.services.event_policy.heuristics import build_event_policy_config
from app.services.event_policy.models import AgentEventData, ChatTurn
from app.services.query_router.schemas import CitationRef
from app.services.retrieval.confidence_engine import (
    ConfidenceResult,
    RerankedItem,
    build_confidence_config,
    compute_confidence,
)
from app.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from app.services.retrieval.schemas import RetrievalCandidate, RetrievalResult

logger = get_logger(__name__)

# Status when Prompt Construction / answer LLM is not wired yet.
PENDING_LLM_STATUS = "pending_llm_pipeline"
COMPLETED_STATUS = "completed"
SQL_DIRECT_STATUS = "sql_agent_direct"


@dataclass(slots=True)
class AnswerGenerationResult:
    """Output of Prompt Construction + main answer LLM (+ optional citations)."""

    answer: str | None
    citation_refs: list[CitationRef] = field(default_factory=list)
    model_used: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: Decimal | None = None
    latency_ms: int | None = None
    verify: bool = False
    # Context Assembly may add bounded neighbor/coverage chunks (RAG
    # answer-quality P1, §4/§7) that were not part of the raw reranked
    # retrieval passed in. These are persisted into ``retrievals`` too so
    # Citation Verification can resolve citation_ids pointing at them.
    expansion_items: list[RetrievalCandidate] = field(default_factory=list)
    # Raw LLM citation_ids (including unknowns) for Citation Verification.
    raw_citation_ids: list[str] = field(default_factory=list)


class AnswerGeneratorPort(Protocol):
    """Main answer LLM path (Prompt Construction → LLM → Citation Verification).

    FR14 / docs §6.2:
      - This port is the **only** call that generates the user-facing answer.
      - Rewrite Agent may call a lightweight model (Haiku) beforehand; that call
        is an explicit exception and must be counted separately in
        ``llm_calls_count`` but is **not** this answer-generation LLM.
    """

    async def generate(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        retrieval_result: RetrievalResult,
        confidence: ConfidenceResult,
        agent_triggered: bool = False,
        chat_history: Sequence[Any] | None = None,
        message_id: UUID | None = None,
    ) -> AnswerGenerationResult: ...


@dataclass(slots=True)
class ComplexPipelineResult:
    """Complex-branch outcome for QueryOrchestrator / Chat Service."""

    answer: str | None
    citation_refs: list[CitationRef]
    metadata: dict[str, Any]
    verify: bool
    status: str | None
    confidence_score: float | None
    confidence_level: ConfidenceLevel | None
    agent_triggered: bool
    retrieval_pass_final: int
    llm_calls_count: int
    model_used: str | None
    message_generation_id: UUID | None = None
    agent_event_id: UUID | None = None
    second_retrieval_executed: bool = False
    confidence_score_before: float | None = None
    confidence_level_before: ConfidenceLevel | None = None
    trigger_reason: str | None = None
    agent_type: str | None = None
    low_confidence_after_retry: bool = False


class ComplexQueryPipeline:
    """FR14 Complex Query orchestration (Confidence → Policy → Agents → retry)."""

    def __init__(
        self,
        *,
        settings: Settings,
        hybrid: HybridRetrievalService,
        agent_events: AgentEventRepository,
        retrieval_records: RetrievalRecordRepository,
        observability: QueryObservabilityRepository | None = None,
        rewrite_agent: RewriteAgent,
        graph_agent: GraphAgent,
        sql_agent: SqlAgent,
        answer_generator: AnswerGeneratorPort | None = None,
        retrieval_top_k: int = 10,
    ) -> None:
        self._settings = settings
        self._hybrid = hybrid
        self._agent_events = agent_events
        self._retrieval_records = retrieval_records
        self._observability = observability
        self._rewrite = rewrite_agent
        self._graph = graph_agent
        self._sql = sql_agent
        self._answer_generator = answer_generator
        self._top_k = max(1, int(retrieval_top_k))
        self._citation_verifier = CitationVerificationService()

    async def run(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        message_id: UUID,
        initial_retrieval: RetrievalResult | None = None,
        assistant_message_id: UUID | None = None,
        chat_history: Sequence[ChatTurn | dict[str, str]] | None = None,
    ) -> ComplexPipelineResult:
        """Execute FR14 complex pipeline for one user question.

        FR14 RETRY LIMIT (do not relax — prevents infinite agent/retrieval loops):
          - At most **one** Micro Agent invocation per Complex Query.
          - At most **one** Second Retrieval (pass=2) per Complex Query.
          - After Second Retrieval, always continue to Prompt Construction / LLM
            even if confidence remains LOW. Never call decide_agent / agents again.
        """
        # --- Pass 1: Hybrid + Rerank (reuse router probe when provided) ---
        try:
            pass1 = initial_retrieval or await self._hybrid.retrieve(
                workspace_id, query_text, top_k=self._top_k
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("complex_pass1_retrieval_failed", error=str(exc))
            pass1 = RetrievalResult(items=[], latency_ms=0, sources_used=[])

        await self._safe_persist_retrievals(message_id, pass1.items, retrieval_pass=1)

        conf_cfg = build_confidence_config(self._settings)
        confidence = compute_confidence(_to_reranked(pass1.items), conf_cfg)
        confidence_before = confidence
        get_fr14_metrics().record_confidence(level=confidence.confidence_level.value)
        active_retrieval = pass1
        active_query = query_text
        agent_triggered = False
        agent_event_id: UUID | None = None
        second_retrieval_executed = False
        # Rewrite Agent lightweight-model call count (NOT the answer LLM).
        rewrite_llm_calls = 0
        sql_answer: str | None = None
        sql_direct = False
        selected_agent_type: str | None = None
        selected_trigger: str | None = None
        event_data: AgentEventData | None = None

        logger.info(
            "confidence_evaluated",
            route_type=RouteType.complex.value,
            message_id=str(message_id),
            workspace_id=str(workspace_id),
            confidence_level=confidence.confidence_level.value,
            confidence_score=confidence.confidence_score,
            retrieval_pass=1,
        )

        if confidence.confidence_level is ConfidenceLevel.low:
            agent_triggered = True
            policy_cfg = build_event_policy_config(self._settings)
            decision = decide_agent(
                query_text,
                _to_reranked(pass1.items),
                RouteType.complex.value,
                config=policy_cfg,
            )
            selected_agent_type = decision.agent_type.value
            selected_trigger = decision.trigger_reason.value
            logger.info(
                "agent_selected",
                agent_type=selected_agent_type,
                trigger_reason=selected_trigger,
                message_id=str(message_id),
                workspace_id=str(workspace_id),
                route_type=RouteType.complex.value,
            )

            event_data, rewrite_llm_calls, sql_answer, sql_direct, active_query = (
                await self._run_selected_agent(
                    decision_agent=decision.agent_type,
                    trigger_reason=decision.trigger_reason,
                    workspace_id=workspace_id,
                    query_text=query_text,
                    pass1_items=pass1.items,
                    confidence_score=confidence.confidence_score,
                    chat_history=chat_history,
                )
            )

            get_fr14_metrics().record_agent(
                agent_type=event_data.agent_type.value,
                trigger_reason=event_data.trigger_reason.value,
                latency_ms=event_data.latency_ms,
                cost_usd=float(event_data.cost_usd or 0),
            )

            # INSERT agent_events immediately after agent (before optional pass=2).
            agent_event_id = await self._safe_insert_agent_event(
                message_id=message_id,
                event=event_data,
                triggered_second_retrieval=False,
            )

            # --- Optional Second Retrieval (ONCE) for Rewrite / Graph ---
            should_retry = (
                not event_data.skip_second_retrieval
                and decision.agent_type in {AgentType.rewrite, AgentType.graph}
                and not sql_direct
            )
            if should_retry:
                # Second Retrieval + Second Re-ranking — single attempt only.
                try:
                    pass2 = await self._hybrid.retrieve(
                        workspace_id, active_query, top_k=self._top_k
                    )
                    await self._safe_persist_retrievals(
                        message_id, pass2.items, retrieval_pass=2
                    )
                    active_retrieval = pass2
                    second_retrieval_executed = True
                    confidence = compute_confidence(_to_reranked(pass2.items), conf_cfg)
                    if agent_event_id is not None:
                        await self._safe_mark_second_retrieval(agent_event_id)
                    logger.info(
                        "second_retrieval",
                        retrieval_pass=2,
                        confidence_level=confidence.confidence_level.value,
                        confidence_score=confidence.confidence_score,
                        retry_executed=True,
                        message_id=str(message_id),
                        workspace_id=str(workspace_id),
                    )
                except Exception as exc:  # noqa: BLE001
                    # Fallback to pass=1 context — do not retry again.
                    logger.warning(
                        "complex_second_retrieval_failed_fallback_pass1",
                        error=str(exc),
                    )
                    active_retrieval = pass1
                    second_retrieval_executed = False

            # After Second Retrieval: even if confidence still LOW, continue to
            # Prompt Construction / LLM. Do NOT invoke Event Policy / agents again.

            _log_agent_triggered(
                workspace_id=workspace_id,
                message_id=message_id,
                confidence_before=confidence_before,
                confidence_after=confidence,
                event_data=event_data,
                second_retrieval=second_retrieval_executed,
                llm_calls_so_far=rewrite_llm_calls,
            )

        low_after_retry = (
            agent_triggered
            and second_retrieval_executed
            and confidence.confidence_level is ConfidenceLevel.low
        )

        # --- SQL Agent direct answer (same shape as Metadata Query) ---
        if sql_direct and sql_answer:
            result = ComplexPipelineResult(
                answer=sql_answer,
                citation_refs=[],
                metadata={
                    "route_type": RouteType.complex.value,
                    "agent_type": AgentType.sql.value,
                    "sql_direct": True,
                },
                verify=True,
                status=SQL_DIRECT_STATUS,
                confidence_score=confidence.confidence_score,
                confidence_level=confidence.confidence_level,
                agent_triggered=agent_triggered,
                retrieval_pass_final=1,
                llm_calls_count=0,
                model_used=None,
                agent_event_id=agent_event_id,
                second_retrieval_executed=False,
                confidence_score_before=confidence_before.confidence_score,
                confidence_level_before=confidence_before.confidence_level,
                trigger_reason=selected_trigger,
                agent_type=selected_agent_type,
                low_confidence_after_retry=False,
            )
            result.message_generation_id = await self._safe_write_generation(
                assistant_message_id or message_id,
                result,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost_usd=Decimal("0"),
                latency_ms=0,
            )
            logger.info(
                "pipeline_done",
                llm_calls_count=0,
                retrieval_pass=1,
                agent_triggered=True,
                sql_direct=True,
                message_id=str(message_id),
                workspace_id=str(workspace_id),
            )
            return result

        # --- Prompt Construction → main answer LLM (at most once) ---
        answer_result = await self._generate_answer(
            workspace_id=workspace_id,
            query_text=active_query,
            retrieval_result=active_retrieval,
            confidence=confidence,
            agent_triggered=agent_triggered,
            chat_history=chat_history,
            message_id=message_id,
        )
        pass_for_expansion = 2 if second_retrieval_executed else 1
        if answer_result is not None and answer_result.expansion_items:
            # Context Assembly's bounded neighbor/coverage chunks (§4/§7) were
            # shown to the LLM but are not part of the raw reranked retrieval
            # already persisted above — persist them too (same pass) so any
            # citation_ids pointing at them resolve during Citation Verification.
            await self._safe_persist_retrievals(
                message_id, answer_result.expansion_items, retrieval_pass=pass_for_expansion
            )

        # llm_calls_count = Rewrite lightweight calls (0|1) + main answer LLM (0|1).
        # Rewrite Agent is the only allowed extra lightweight-model call; it does
        # NOT count as the FR4 answer-generation LLM (docs §6.2).
        main_llm_calls = 1 if answer_result is not None else 0
        llm_calls_count = int(rewrite_llm_calls) + int(main_llm_calls)
        pass_final = 2 if second_retrieval_executed else 1

        if answer_result is None:
            result = ComplexPipelineResult(
                answer=None,
                citation_refs=[],
                metadata={
                    "route_type": RouteType.complex.value,
                    "status": PENDING_LLM_STATUS,
                    "retrieval_item_count": len(active_retrieval.items),
                    "second_retrieval_executed": second_retrieval_executed,
                    "low_confidence_after_retry": low_after_retry,
                },
                verify=False,
                status=PENDING_LLM_STATUS,
                confidence_score=confidence.confidence_score,
                confidence_level=confidence.confidence_level,
                agent_triggered=agent_triggered,
                retrieval_pass_final=pass_final,
                llm_calls_count=llm_calls_count,
                model_used=None,
                agent_event_id=agent_event_id,
                second_retrieval_executed=second_retrieval_executed,
                confidence_score_before=confidence_before.confidence_score,
                confidence_level_before=confidence_before.confidence_level,
                trigger_reason=selected_trigger,
                agent_type=selected_agent_type,
                low_confidence_after_retry=low_after_retry,
            )
        else:
            verified_answer, verified_refs, verify_flag = await self._verify_llm_citations(
                workspace_id=workspace_id,
                message_id=message_id,
                retrieval_result=active_retrieval,
                answer_result=answer_result,
            )
            result = ComplexPipelineResult(
                answer=verified_answer,
                citation_refs=verified_refs,
                metadata={
                    "route_type": RouteType.complex.value,
                    "second_retrieval_executed": second_retrieval_executed,
                    "retrieval_item_count": len(active_retrieval.items),
                    "low_confidence_after_retry": low_after_retry,
                },
                verify=verify_flag,
                status=COMPLETED_STATUS if verified_answer else PENDING_LLM_STATUS,
                confidence_score=confidence.confidence_score,
                confidence_level=confidence.confidence_level,
                agent_triggered=agent_triggered,
                retrieval_pass_final=pass_final,
                llm_calls_count=llm_calls_count,
                model_used=answer_result.model_used,
                agent_event_id=agent_event_id,
                second_retrieval_executed=second_retrieval_executed,
                confidence_score_before=confidence_before.confidence_score,
                confidence_level_before=confidence_before.confidence_level,
                trigger_reason=selected_trigger,
                agent_type=selected_agent_type,
                low_confidence_after_retry=low_after_retry,
            )
            result.message_generation_id = await self._safe_write_generation(
                assistant_message_id or message_id,
                result,
                prompt_tokens=answer_result.prompt_tokens,
                completion_tokens=answer_result.completion_tokens,
                total_tokens=answer_result.total_tokens,
                cost_usd=answer_result.cost_usd,
                latency_ms=answer_result.latency_ms,
            )

        logger.info(
            "pipeline_done",
            confidence_level=(
                result.confidence_level.value if result.confidence_level else None
            ),
            llm_calls_count=result.llm_calls_count,
            retrieval_pass=result.retrieval_pass_final,
            agent_triggered=result.agent_triggered,
            retry_executed=result.second_retrieval_executed,
            low_confidence_after_retry=low_after_retry,
            message_id=str(message_id),
            workspace_id=str(workspace_id),
            route_type=RouteType.complex.value,
        )
        return result

    async def _run_selected_agent(
        self,
        *,
        decision_agent: AgentType,
        trigger_reason: Any,
        workspace_id: UUID,
        query_text: str,
        pass1_items: list[RetrievalCandidate],
        confidence_score: float | None,
        chat_history: Sequence[ChatTurn | dict[str, str]] | None,
    ) -> tuple[AgentEventData, int, str | None, bool, str]:
        """Run exactly one agent. Returns event, rewrite_llm_calls, sql fields, query."""
        rewrite_llm_calls = 0
        sql_answer: str | None = None
        sql_direct = False
        active_query = query_text

        try:
            if decision_agent is AgentType.rewrite:
                rewrite_result = self._rewrite.run(
                    original_query=query_text,
                    trigger_reason=trigger_reason,
                    chat_history=chat_history,
                    confidence_score=confidence_score,
                )
                event_data = rewrite_result.event
                active_query = rewrite_result.rewritten_query or query_text
                # Count Rewrite Haiku only when a model was actually invoked.
                if event_data.model_used and event_data.success:
                    rewrite_llm_calls = 1
                elif event_data.model_used and not event_data.success:
                    # Attempted call that failed — still an LLM attempt for accounting.
                    rewrite_llm_calls = 1 if event_data.error else 0
            elif decision_agent is AgentType.graph:
                graph_result = self._graph.run(
                    workspace_id=workspace_id,
                    query_text=query_text,
                    trigger_reason=trigger_reason,
                    reranked_results=_to_reranked(pass1_items),
                    confidence_score=confidence_score,
                )
                event_data = graph_result.event
            else:
                sql_result = await self._sql.run(
                    workspace_id=workspace_id,
                    query_text=query_text,
                    trigger_reason=trigger_reason,
                    confidence_score=confidence_score,
                )
                event_data = sql_result.event
                if (
                    not sql_result.fallback_to_complex
                    and sql_result.answer
                    and sql_result.skip_second_retrieval
                ):
                    sql_answer = sql_result.answer
                    sql_direct = True
        except Exception as exc:  # noqa: BLE001 — continue with pass-1 context
            logger.warning("complex_agent_failed_continue", error=str(exc))
            event_data = AgentEventData(
                agent_type=decision_agent,
                trigger_reason=trigger_reason,
                model_used=None,
                cost_usd=Decimal("0"),
                latency_ms=0,
                input_payload={"original_query": query_text},
                output_payload={"error": type(exc).__name__},
                confidence_score=confidence_score,
                triggered_second_retrieval=False,
                skip_second_retrieval=False,
                success=False,
                error=type(exc).__name__,
            )

        return event_data, rewrite_llm_calls, sql_answer, sql_direct, active_query

    async def _verify_llm_citations(
        self,
        *,
        workspace_id: UUID,
        message_id: UUID,
        retrieval_result: RetrievalResult,
        answer_result: AnswerGenerationResult,
    ) -> tuple[str | None, list[CitationRef], bool]:
        """Run FR5 Citation Verification on the LLM answer before Chat persist/stream."""
        original = (answer_result.answer or "").strip() or None
        if original is None:
            return None, [], False

        cited_ids = list(answer_result.raw_citation_ids)
        if not cited_ids:
            cited_ids = [
                str(ref.chunk_id)
                for ref in answer_result.citation_refs
                if ref.chunk_id is not None
            ]
        if not cited_ids and answer_result.model_used is None:
            # Provider-not-configured / non-LLM answer — not a factual claim.
            return original, [], False

        evidence = await self._load_verification_evidence(
            workspace_id=workspace_id,
            message_id=message_id,
            retrieval_result=retrieval_result,
            expansion_items=answer_result.expansion_items,
            cited_ids=cited_ids,
        )
        snippet_map = {
            str(ref.chunk_id): ref.text_snippet
            for ref in answer_result.citation_refs
            if ref.chunk_id is not None and ref.text_snippet
        }
        report = self._citation_verifier.verify(
            workspace_id=workspace_id,
            message_id=message_id,
            cited_ids=cited_ids,
            evidence=evidence,
            snippet_by_citation_id=snippet_map,
        )
        verified_refs = self._citation_verifier.to_citation_refs(report)
        if not report.has_verified:
            logger.info(
                "citation_verification_fallback",
                workspace_id=str(workspace_id),
                message_id=str(message_id),
                invalid_count=report.invalid_count,
            )
            return INSUFFICIENT_EVIDENCE_ANSWER, [], False

        rewritten = rewrite_inline_citation_markers(
            original,
            [str(ref.chunk_id) for ref in verified_refs if ref.chunk_id is not None],
        ) or original
        return rewritten, verified_refs, True

    async def _load_verification_evidence(
        self,
        *,
        workspace_id: UUID,
        message_id: UUID,
        retrieval_result: RetrievalResult,
        expansion_items: Sequence[RetrievalCandidate],
        cited_ids: Sequence[str],
    ) -> list:
        """Retrieved-context text + lightweight integrity joins for cited chunks only."""
        candidates = list(retrieval_result.items) + list(expansion_items or [])
        retrieved = evidence_from_candidates(
            workspace_id=workspace_id,
            message_id=message_id,
            candidates=candidates,
        )
        chunk_ids = _parse_chunk_uuids(cited_ids)
        persisted = []
        loader = getattr(self._retrieval_records, "list_integrity_for_cited_chunks", None)
        if loader is not None and chunk_ids:
            try:
                persisted = await loader(message_id=message_id, chunk_ids=chunk_ids)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "citation_verification_evidence_load_failed",
                    error=type(exc).__name__,
                )
                persisted = []
        return merge_retrieved_and_persisted_evidence(
            retrieved=retrieved,
            persisted=persisted,
        )

    async def _generate_answer(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        retrieval_result: RetrievalResult,
        confidence: ConfidenceResult,
        agent_triggered: bool = False,
        chat_history: Sequence[ChatTurn | dict[str, str]] | None = None,
        message_id: UUID | None = None,
    ) -> AnswerGenerationResult | None:
        if self._answer_generator is None:
            return None
        history_dicts: list[dict[str, str]] | None = None
        if chat_history:
            history_dicts = []
            for turn in chat_history:
                if isinstance(turn, dict):
                    history_dicts.append(
                        {
                            "role": str(turn.get("role") or ""),
                            "content": str(turn.get("content") or ""),
                        }
                    )
                else:
                    history_dicts.append(
                        {"role": str(turn.role), "content": str(turn.content)}
                    )
        try:
            return await self._answer_generator.generate(
                workspace_id=workspace_id,
                query_text=query_text,
                retrieval_result=retrieval_result,
                confidence=confidence,
                agent_triggered=agent_triggered,
                chat_history=history_dicts,
                message_id=message_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("complex_answer_generator_failed", error=str(exc))
            return AnswerGenerationResult(answer=None, verify=False)

    async def _safe_persist_retrievals(
        self,
        message_id: UUID,
        items: Sequence[RetrievalCandidate],
        *,
        retrieval_pass: int,
    ) -> None:
        try:
            await self._retrieval_records.insert_candidates(
                message_id=message_id,
                candidates=items,
                retrieval_pass=retrieval_pass,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "complex_persist_retrievals_failed",
                retrieval_pass=retrieval_pass,
                error=str(exc),
            )

    async def _safe_insert_agent_event(
        self,
        *,
        message_id: UUID,
        event: AgentEventData,
        triggered_second_retrieval: bool,
    ) -> UUID | None:
        try:
            row = await self._agent_events.insert_from_event_data(
                message_id=message_id,
                event=event,
                triggered_second_retrieval=triggered_second_retrieval,
            )
            return row.id
        except Exception as exc:  # noqa: BLE001
            logger.warning("complex_persist_agent_event_failed", error=str(exc))
            return None

    async def _safe_mark_second_retrieval(self, event_id: UUID) -> None:
        try:
            await self._agent_events.mark_second_retrieval(event_id, value=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("complex_mark_second_retrieval_failed", error=str(exc))

    async def _safe_write_generation(
        self,
        message_id: UUID,
        result: ComplexPipelineResult,
        *,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
        cost_usd: Decimal | None,
        latency_ms: int | None,
    ) -> UUID | None:
        if self._observability is None:
            return None
        try:
            row = await self._observability.create_message_generation(
                message_id=message_id,
                route_type=RouteType.complex,
                model_used=result.model_used,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                confidence_level=result.confidence_level,
                confidence_score=result.confidence_score,
                agent_triggered=result.agent_triggered,
            )
            return row.id
        except Exception as exc:  # noqa: BLE001
            logger.warning("complex_persist_message_generation_failed", error=str(exc))
            return None


def _parse_chunk_uuids(cited_ids: Sequence[str]) -> list[UUID]:
    """Keep only parseable unique chunk UUIDs for the integrity join."""
    out: list[UUID] = []
    seen: set[UUID] = set()
    for raw in cited_ids:
        try:
            cid = UUID(str(raw).strip())
        except (ValueError, TypeError, AttributeError):
            continue
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def _to_reranked(items: Sequence[RetrievalCandidate]) -> list[RerankedItem]:
    out: list[RerankedItem] = []
    for item in items:
        out.append(
            RerankedItem(
                score=item.score,
                rank=item.rank,
                document_id=str(item.document_id) if item.document_id else None,
                entity_id=str(item.entity_id) if item.entity_id else None,
            )
        )
    return out


def _log_agent_triggered(
    *,
    workspace_id: UUID,
    message_id: UUID,
    confidence_before: ConfidenceResult,
    confidence_after: ConfidenceResult,
    event_data: AgentEventData,
    second_retrieval: bool,
    llm_calls_so_far: int,
) -> None:
    """Structured JSON log for agent path — no prompts / document / payloads."""
    logger.info(
        "agent_triggered",
        query_id=str(message_id),
        workspace_id=str(workspace_id),
        message_id=str(message_id),
        route_type=RouteType.complex.value,
        confidence_before=confidence_before.confidence_score,
        confidence_after=confidence_after.confidence_score,
        confidence_level_before=confidence_before.confidence_level.value,
        confidence_level_after=confidence_after.confidence_level.value,
        trigger_reason=event_data.trigger_reason.value,
        agent_type=event_data.agent_type.value,
        triggered_second_retrieval=second_retrieval,
        retrieval_pass=2 if second_retrieval else 1,
        model_used=event_data.model_used,
        cost_usd=float(event_data.cost_usd or 0),
        latency_ms=event_data.latency_ms,
        llm_calls_count=llm_calls_so_far,
        second_retrieval=second_retrieval,
    )