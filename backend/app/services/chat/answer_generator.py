# =============================================================================
# File: answer_generator.py
# Module/Service: Chat Service / Prompt Construction (FR4)
# Layer: Service
# Purpose: AnswerGeneratorPort — build_prompt → 1 structured LLM → citation map.
# Responsibilities:
#   - Model tiering from Settings; structured {answer, citation_ids}
#   - Map citation_ids against latest-pass retrieval items only (membership
#     pre-filter). Citation Verification Layer owns verified=True.
#   - Structured stage logging (llm_request_started / llm_response_received /
#     llm_structured_output_parsed / chat_answer_llm_failed) — no prompt or
#     document content in logs, ever
# Dependencies:
#   - prompt_builder, model_tiering, chat_llm, Settings
# Public Exports:
#   - PromptAnswerGenerator
# Database/Table: N/A (persistence owned by ComplexQueryPipeline / MessageService)
# Related Modules: ComplexQueryPipeline.answer_generator
# Important Notes: Exactly one answer LLM call; Rewrite Agent is separate.
#   Provider selected via CHAT_LLM_PROVIDER (anthropic | openai). Provider
#   failures (incl. EmptyCompletionError) are re-raised here — never coerced
#   into ``answer=""`` — so the caller (ComplexQueryPipeline) can classify and
#   fall back deterministically without a second LLM call.
#   Citation Verification is a separate layer — this class only maps ids.
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.adapters.chat_llm import extract_structured_json_async, resolve_chat_llm
from app.core.config import Settings
from app.core.logging import get_logger
from app.services.chat.complex_query_pipeline import AnswerGenerationResult
from app.services.chat.context_assembly import (
    ChunkContextPort,
    ContextAssemblyConfig,
    assemble_context,
)
from app.services.chat.model_tiering import estimate_answer_cost_usd, select_answer_model
from app.services.chat.prompt_builder import (
    build_prompt,
    retrieval_candidates_to_prompt_items,
)
from app.services.chat.prompt_templates import ANSWER_SYSTEM_PROMPT
from app.services.query_router.schemas import CitationRef
from app.services.retrieval.confidence_engine import ConfidenceResult
from app.services.retrieval.schemas import RetrievalResult

logger = get_logger(__name__)


class PromptAnswerGenerator:
    """Production AnswerGeneratorPort backed by configured chat LLM provider."""

    def __init__(
        self,
        settings: Settings,
        *,
        llm_call: Any | None = None,
        context_port: ChunkContextPort | None = None,
    ) -> None:
        self._settings = settings
        # Injectable for tests. Signature: async (**kwargs) -> StructuredLlmResult-like.
        # When None, uses chat_llm.extract_structured_json_async (provider-aware).
        self._llm_call = llm_call
        # Optional bounded neighbor/coverage expansion (context_assembly.py).
        # None disables expansion but grouping/ordering/dedup still run.
        self._context_port = context_port

    async def generate(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
        retrieval_result: RetrievalResult,
        confidence: ConfidenceResult,
        agent_triggered: bool = False,
        chat_history: Sequence[dict[str, str]] | None = None,
        message_id: UUID | None = None,
    ) -> AnswerGenerationResult:
        """Run Prompt Construction + exactly one answer LLM call."""
        del message_id  # reserved for DB latest-pass verification in Part 2.5
        settings = self._settings
        if resolve_chat_llm(settings) is None and self._llm_call is None:
            logger.warning(
                "chat_answer_llm_missing_api_key",
                workspace_id=str(workspace_id),
                provider=str(settings.chat_llm_provider),
            )
            return AnswerGenerationResult(
                answer="I cannot generate an answer because the LLM provider is not configured.",
                citation_refs=[],
                model_used=None,
                verify=False,
            )

        # In-memory retrieval_result is already the active (latest) pass from
        # pipeline. Context Assembly (dedup + bounded neighbor/coverage
        # expansion + grouping/ordering) runs BEFORE Prompt Construction —
        # RAG answer-quality P1, spec §4-§6, §16-§18. Still exactly 1 LLM call.
        assembly = await assemble_context(
            query_text,
            retrieval_result.items,
            workspace_id=workspace_id,
            port=self._context_port if settings.context_assembly_enabled else None,
            config=ContextAssemblyConfig(
                neighbor_window=int(settings.context_neighbor_window),
                max_neighbor_seeds=int(settings.context_max_neighbor_seeds),
                max_context_chunks=int(settings.context_max_chunks),
                coverage_min_sections=int(settings.context_coverage_min_sections),
                coverage_max_chunks=int(settings.context_coverage_max_chunks),
            ),
            candidate_count=retrieval_result.candidate_count,
            reranked_count=retrieval_result.reranked_count,
        )
        logger.info(
            "retrieval_quality_debug",
            workspace_id=str(workspace_id),
            query_type=assembly.debug.query_type,
            candidate_count=assembly.debug.candidate_count,
            reranked_count=assembly.debug.reranked_count,
            unique_documents=assembly.debug.unique_documents,
            unique_sections=assembly.debug.unique_sections,
            neighbor_expansion_count=assembly.debug.neighbor_expansion_count,
            coverage_expansion_count=assembly.debug.coverage_expansion_count,
            duplicate_count=assembly.debug.duplicate_count,
            final_context_chunks=assembly.debug.final_context_chunks,
            final_context_tokens=assembly.debug.final_context_tokens,
            coverage_score=assembly.debug.coverage_score,
        )
        prompt_items = retrieval_candidates_to_prompt_items(assembly.items)
        built = build_prompt(
            ANSWER_SYSTEM_PROMPT,
            list(chat_history) if chat_history else None,
            prompt_items,
            query_text,
        )
        model = select_answer_model(
            settings,
            agent_triggered=agent_triggered,
            prefer_strong=False,
        )
        started = time.perf_counter()
        call_kwargs = {
            "system": built.system,
            "user": built.user,
            "model": model,
            "max_tokens": int(settings.chat_answer_max_tokens),
            "temperature": float(settings.chat_answer_temperature),
            "top_p": float(settings.chat_answer_top_p),
            "timeout_seconds": float(settings.chat_answer_timeout_seconds),
            "cost_estimator": lambda input_tokens, output_tokens: estimate_answer_cost_usd(
                settings,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        }
        logger.info(
            "llm_request_started",
            workspace_id=str(workspace_id),
            provider=str(settings.chat_llm_provider),
            model_used=model,
            agent_triggered=agent_triggered,
            context_chunks=len(prompt_items),
        )
        try:
            if self._llm_call is not None:
                llm = await self._llm_call(**call_kwargs)
            else:
                llm = await extract_structured_json_async(
                    settings=settings,
                    **call_kwargs,
                )
        except Exception as exc:  # noqa: BLE001 — classify + log, never swallow silently
            logger.warning(
                "chat_answer_llm_failed",
                workspace_id=str(workspace_id),
                provider=str(settings.chat_llm_provider),
                model_used=model,
                error=type(exc).__name__,
                detail=str(exc),
                latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
            )
            raise

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        # getattr: self._llm_call is injectable (tests use duck-typed stand-ins
        # that may predate the finish_reason field on StructuredLlmResult).
        finish_reason = getattr(llm, "finish_reason", None)
        logger.info(
            "llm_response_received",
            workspace_id=str(workspace_id),
            provider=str(settings.chat_llm_provider),
            model_used=str(llm.model or model),
            finish_reason=finish_reason,
            prompt_tokens=int(llm.input_tokens),
            completion_tokens=int(llm.output_tokens),
            latency_ms=latency_ms,
        )
        data = llm.data if isinstance(llm.data, dict) else {}
        answer = str(data.get("answer") or "").strip() or None
        raw_ids = data.get("citation_ids") or []
        if not isinstance(raw_ids, list):
            raw_ids = []
        allowed = {item.citation_id for item in prompt_items}
        # by_chunk must reflect what was actually shown in the prompt —
        # assembly.items includes bounded neighbor/coverage expansion chunks
        # that are not present in the raw (pre-assembly) retrieval_result.
        by_chunk = {
            str(c.chunk_id): c
            for c in assembly.items
            if getattr(c, "chunk_id", None) is not None
        }
        citation_refs: list[CitationRef] = []
        seen_chunk: set[str] = set()
        for raw in raw_ids:
            cid = str(raw).strip()
            if cid not in allowed or cid in seen_chunk:
                continue
            cand = by_chunk.get(cid)
            if cand is None:
                continue
            citation_refs.append(
                CitationRef(
                    chunk_id=cand.chunk_id,
                    document_id=cand.document_id,
                    page_number=cand.page_number,
                    verify=False,  # Citation Verification Layer owns this flag
                    text_snippet=(cand.text_snippet or "").strip() or None,
                )
            )
            seen_chunk.add(cid)
        # Inline [uuid] → [n] rewrite happens AFTER Citation Verification so
        # presentation indexes match the verified subset only.
        raw_citation_ids = [str(item).strip() for item in raw_ids if str(item).strip()]
        logger.info(
            "llm_structured_output_parsed",
            workspace_id=str(workspace_id),
            has_answer=bool(answer),
            raw_citation_id_count=len(raw_citation_ids),
            mapped_citation_id_count=len(citation_refs),
        )

        total_tokens = int(llm.input_tokens) + int(llm.output_tokens)
        original_chunk_ids = {
            str(c.chunk_id) for c in retrieval_result.items if getattr(c, "chunk_id", None)
        }
        expansion_items = [
            c
            for c in assembly.items
            if getattr(c, "chunk_id", None) is not None
            and str(c.chunk_id) not in original_chunk_ids
        ]
        return AnswerGenerationResult(
            answer=answer,
            citation_refs=citation_refs,
            model_used=str(llm.model or model),
            prompt_tokens=int(llm.input_tokens),
            completion_tokens=int(llm.output_tokens),
            total_tokens=total_tokens,
            cost_usd=Decimal(str(llm.estimated_cost_usd)),
            latency_ms=latency_ms,
            verify=False,
            expansion_items=expansion_items,
            raw_citation_ids=raw_citation_ids,
        )
