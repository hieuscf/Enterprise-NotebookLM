# =============================================================================
# File: answer_generator.py
# Module/Service: Chat Service / Prompt Construction (FR4)
# Layer: Service
# Purpose: AnswerGeneratorPort — build_prompt → 1 structured LLM → citation map.
# Responsibilities:
#   - Model tiering from Settings; structured {answer, citation_ids}
#   - Map citation_ids against latest-pass retrieval items only
# Dependencies:
#   - prompt_builder, model_tiering, anthropic_client, Settings
# Public Exports:
#   - PromptAnswerGenerator
# Database/Table: N/A (persistence owned by ComplexQueryPipeline / MessageService)
# Related Modules: ComplexQueryPipeline.answer_generator
# Important Notes: Exactly one answer LLM call; Rewrite Agent is separate.
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.adapters.anthropic_client import extract_structured_json_async
from app.core.config import Settings
from app.core.logging import get_logger
from app.services.chat.complex_query_pipeline import AnswerGenerationResult
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
    """Production AnswerGeneratorPort backed by Anthropic structured JSON."""

    def __init__(
        self,
        settings: Settings,
        *,
        llm_call: Any | None = None,
    ) -> None:
        self._settings = settings
        # Injectable for tests (async callable with same kwargs as extract_structured_json_async).
        self._llm_call = llm_call or extract_structured_json_async

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
        api_key = (settings.anthropic_api_key or "").strip()
        if not api_key:
            logger.warning("chat_answer_llm_missing_api_key", workspace_id=str(workspace_id))
            return AnswerGenerationResult(
                answer="I cannot generate an answer because the LLM provider is not configured.",
                citation_refs=[],
                model_used=None,
                verify=False,
            )

        # In-memory retrieval_result is already the active (latest) pass from pipeline.
        prompt_items = retrieval_candidates_to_prompt_items(retrieval_result.items)
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
        try:
            llm = await self._llm_call(
                system=built.system,
                user=built.user,
                model=model,
                api_key=api_key,
                api_base=settings.anthropic_api_base,
                max_tokens=int(settings.chat_answer_max_tokens),
                temperature=float(settings.chat_answer_temperature),
                top_p=float(settings.chat_answer_top_p),
                timeout_seconds=float(settings.chat_answer_timeout_seconds),
                cost_estimator=lambda input_tokens, output_tokens: estimate_answer_cost_usd(
                    settings,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "chat_answer_llm_failed",
                workspace_id=str(workspace_id),
                error=type(exc).__name__,
            )
            raise

        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        data = llm.data if isinstance(llm.data, dict) else {}
        answer = str(data.get("answer") or "").strip() or None
        raw_ids = data.get("citation_ids") or []
        if not isinstance(raw_ids, list):
            raw_ids = []
        allowed = {item.citation_id for item in prompt_items}
        by_chunk = {
            str(c.chunk_id): c
            for c in retrieval_result.items
            if getattr(c, "chunk_id", None) is not None
        }
        citation_refs: list[CitationRef] = []
        for raw in raw_ids:
            cid = str(raw).strip()
            if cid not in allowed:
                continue
            cand = by_chunk.get(cid)
            if cand is None:
                continue
            citation_refs.append(
                CitationRef(
                    chunk_id=cand.chunk_id,
                    document_id=cand.document_id,
                    page_number=cand.page_number,
                    verify=True,
                )
            )

        total_tokens = int(llm.input_tokens) + int(llm.output_tokens)
        return AnswerGenerationResult(
            answer=answer,
            citation_refs=citation_refs,
            model_used=str(llm.model or model),
            prompt_tokens=int(llm.input_tokens),
            completion_tokens=int(llm.output_tokens),
            total_tokens=total_tokens,
            cost_usd=Decimal(str(llm.estimated_cost_usd)),
            latency_ms=latency_ms,
            verify=bool(citation_refs) if answer else False,
        )
