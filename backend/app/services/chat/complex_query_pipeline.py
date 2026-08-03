# =============================================================================
# File: complex_query_pipeline.py
# Module/Service: Chat Service / Complex Query Pipeline (FR14)
# Layer: Service
# Purpose: Integrate Confidence Engine + Event Policy + Micro Agents into complex.
# Responsibilities:
#   - Post-rerank confidence; High → Prompt/LLM; Low → agent (+ optional pass=2)
#   - Persist retrievals / agent_events / message_generations confidence fields
#   - Enforce one-agent + one-Second-Retrieval limit (no loops)
# Dependencies:
#   - HybridRetrievalService, confidence_engine, event_policy, agents, repos
# Public Exports:
#   - ComplexQueryPipeline, ComplexPipelineResult, AnswerGeneratorPort
# Database/Table: retrievals, agent_events, message_generations
# Related Modules: QueryOrchestrator (complex branch), Prompt Construction
# Important Notes:
#   - Only for route_type=complex. Does not alter Query Router classification.
#   - Rewrite Agent Haiku is the sole lightweight-model exception (not answer LLM).
# =============================================================================

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enums import AgentType, ConfidenceLevel, RouteType
from app.repositories.agent_events import AgentEventRepository
from app.repositories.query_logs import QueryObservabilityRepository
from app.repositories.retrieval_records import RetrievalRecordRepository
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
        active_retrieval = pass1
        active_query = query_text
        agent_triggered = False
        agent_event_id: UUID | None = None
        second_retrieval_executed = False
        # Rewrite Agent lightweight-model call count (NOT the answer LLM).
        rewrite_llm_calls = 0
        sql_answer: str | None = None
        sql_direct = False

        logger.info(
            "complex_confidence",
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
            logger.info(
                "complex_agent_selected",
                agent_type=decision.agent_type.value,
                trigger_reason=decision.trigger_reason.value,
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
                        "complex_second_retrieval",
                        retrieval_pass=2,
                        confidence_level=confidence.confidence_level.value,
                        confidence_score=confidence.confidence_score,
                        retry_executed=True,
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
                "complex_pipeline_done",
                llm_calls_count=0,
                retrieval_pass=1,
                agent_triggered=True,
                sql_direct=True,
            )
            return result

        # --- Prompt Construction → main answer LLM (at most once) ---
        answer_result = await self._generate_answer(
            workspace_id=workspace_id,
            query_text=active_query,
            retrieval_result=active_retrieval,
            confidence=confidence,
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
            )
        else:
            result = ComplexPipelineResult(
                answer=answer_result.answer,
                citation_refs=list(answer_result.citation_refs),
                metadata={
                    "route_type": RouteType.complex.value,
                    "second_retrieval_executed": second_retrieval_executed,
                    "retrieval_item_count": len(active_retrieval.items),
                },
                verify=bool(answer_result.verify),
                status=COMPLETED_STATUS if answer_result.answer else PENDING_LLM_STATUS,
                confidence_score=confidence.confidence_score,
                confidence_level=confidence.confidence_level,
                agent_triggered=agent_triggered,
                retrieval_pass_final=pass_final,
                llm_calls_count=llm_calls_count,
                model_used=answer_result.model_used,
                agent_event_id=agent_event_id,
                second_retrieval_executed=second_retrieval_executed,
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
            "complex_pipeline_done",
            confidence_level=(
                result.confidence_level.value if result.confidence_level else None
            ),
            llm_calls_count=result.llm_calls_count,
            retrieval_pass=result.retrieval_pass_final,
            agent_triggered=result.agent_triggered,
            retry_executed=result.second_retrieval_executed,
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

    async def _generate_answer(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        retrieval_result: RetrievalResult,
        confidence: ConfidenceResult,
    ) -> AnswerGenerationResult | None:
        if self._answer_generator is None:
            return None
        try:
            return await self._answer_generator.generate(
                workspace_id=workspace_id,
                query_text=query_text,
                retrieval_result=retrieval_result,
                confidence=confidence,
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
