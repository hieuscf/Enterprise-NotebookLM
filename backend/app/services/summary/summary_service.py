# =============================================================================
# File: summary_service.py
# Module/Service: Summary Service (FR6)
# Layer: Service
# Purpose: Generate AI summaries for the current document version (UC5).
# Responsibilities:
#   - Resolve current document version + chunks (and topics for by_topic)
#   - Select model via shared model-tiering; budget tokens to context window
#   - Exactly one chat-LLM call via adapter; persist Summary + observability
# Dependencies:
#   - DocumentRepository, RetrievalRepository, SummaryRepository
#   - chat_llm adapter, model_tiering, count_tokens
# Public Exports:
#   - SummaryService, SummaryServiceError
# Database/Table: summaries, documents, document_versions, document_chunks,
#   topics, topic_chunks
# Related Modules: app.services.summary.prompts, OpenAPI Summaries
# Important Notes:
#   - API parameter ``style`` maps to ORM/DB column ``type`` (SummaryType).
#   - Content is read from documents.current_version_id only.
#   - No raw SQL/ORM in this layer; LLM only via chat_llm adapter.
# =============================================================================

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any

from app.adapters.chat_llm import extract_structured_json_async, resolve_chat_llm
from app.adapters.llm_result import StructuredLlmResult
from app.ai.tokens import count_tokens, split_text_by_tokens
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.artifacts import Summary
from app.models.enums import DocumentVersionStatus, SummaryStyle, SummaryType
from app.repositories.documents import DocumentRepository
from app.repositories.retrieval import ChunkHydrationRow, RetrievalRepository
from app.repositories.summaries import SummaryRepository, TopicContextRow
from app.services.chat.model_tiering import (
    estimate_answer_cost_usd,
    model_context_window,
    select_answer_model,
)
from app.services.summary.prompts import build_summary_prompts

logger = get_logger(__name__)

# detailed / by_topic benefit from the strong tier; short / bullets stay light.
_STRONG_STYLES: frozenset[SummaryType] = frozenset(
    {SummaryType.detailed, SummaryType.by_topic}
)


class SummaryServiceError(Exception):
    """Domain error mapped to HTTP by the presentation layer."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SummaryService:
    """Application service for FR6 AI Summary generation."""

    def __init__(
        self,
        *,
        settings: Settings,
        documents: DocumentRepository,
        retrieval: RetrievalRepository,
        summaries: SummaryRepository,
        llm_call: Any | None = None,
    ) -> None:
        self._settings = settings
        self._documents = documents
        self._retrieval = retrieval
        self._summaries = summaries
        # Injectable for tests. Signature: async (**kwargs) -> StructuredLlmResult-like.
        self._llm_call = llm_call

    async def generate_summary(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        style: SummaryStyle,
        created_by: uuid.UUID,
    ) -> Summary:
        """Generate and persist a summary for the document's current version.

        Args:
            workspace_id: Tenant scope (required for multi-tenant isolation).
            document_id: Target document.
            style: OpenAPI Summary.style (maps to DB ``type`` / SummaryType).
            created_by: Requesting user id.

        Returns:
            Persisted ``Summary`` ORM row.
        """
        summary_type = SummaryType(style)
        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise SummaryServiceError(
                "not_found", "Document not found", status_code=404
            )
        if document.current_version_id is None:
            raise SummaryServiceError(
                "no_current_version",
                "Document has no current version",
                status_code=409,
            )

        version = await self._documents.get_version(
            workspace_id, document_id, document.current_version_id
        )
        if version is None:
            raise SummaryServiceError(
                "no_current_version",
                "Current document version not found",
                status_code=409,
            )
        if version.status != DocumentVersionStatus.ready:
            raise SummaryServiceError(
                "version_not_ready",
                f"Current version status is {version.status.value}; must be ready",
                status_code=409,
            )

        chunks = await self._retrieval.list_chunks_for_document(
            workspace_id,
            document_id,
            version_id=version.id,
        )
        if not chunks:
            raise SummaryServiceError(
                "no_chunks",
                "Current document version has no chunks to summarize",
                status_code=409,
            )

        topics: list[TopicContextRow] = []
        if summary_type == SummaryType.by_topic:
            topics = await self._summaries.list_topics_for_version(
                workspace_id=workspace_id,
                document_version_id=version.id,
            )

        if resolve_chat_llm(self._settings) is None and self._llm_call is None:
            raise SummaryServiceError(
                "llm_not_configured",
                "Chat LLM provider is not configured",
                status_code=503,
            )

        prefer_strong = summary_type in _STRONG_STYLES
        model = select_answer_model(
            self._settings,
            agent_triggered=False,
            prefer_strong=prefer_strong,
        )
        budgeted_chunks = self._fit_chunks_to_context(
            chunks,
            model=model,
            style=summary_type,
            topics=topics,
            document_title=document.title,
        )
        system, user = build_summary_prompts(
            style=summary_type,
            document_title=document.title,
            chunks=budgeted_chunks,
            topics=topics if summary_type == SummaryType.by_topic else None,
        )

        started = time.perf_counter()
        call_kwargs = {
            "system": system,
            "user": user,
            "model": model,
            "max_tokens": int(self._settings.summary_max_output_tokens),
            "temperature": float(self._settings.chat_answer_temperature),
            "top_p": float(self._settings.chat_answer_top_p),
            "timeout_seconds": float(self._settings.summary_timeout_seconds),
            "cost_estimator": lambda input_tokens, output_tokens: estimate_answer_cost_usd(
                self._settings,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        }
        try:
            if self._llm_call is not None:
                llm = await self._llm_call(**call_kwargs)
            else:
                llm = await extract_structured_json_async(
                    settings=self._settings,
                    **call_kwargs,
                )
        except Exception as exc:  # noqa: BLE001 — map provider failures to domain error
            logger.exception(
                "summary_llm_failed",
                document_id=str(document_id),
                style=summary_type.value,
            )
            raise SummaryServiceError(
                "llm_failed",
                f"Summary generation failed: {exc}",
                status_code=502,
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        content = self._extract_summary_text(llm)
        if not content.strip():
            raise SummaryServiceError(
                "empty_summary",
                "LLM returned an empty summary",
                status_code=502,
            )

        prompt_tokens = int(getattr(llm, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(llm, "output_tokens", 0) or 0)
        cost = Decimal(
            str(round(float(getattr(llm, "estimated_cost_usd", 0.0) or 0.0), 6))
        )
        model_used = str(getattr(llm, "model", None) or model)

        row = await self._summaries.create(
            document_id=document.id,
            created_by=created_by,
            source_version_id=version.id,
            type_=summary_type,
            content=content.strip(),
            model_used=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )
        logger.info(
            "summary_generated",
            document_id=str(document_id),
            summary_id=str(row.id),
            style=summary_type.value,
            source_version_id=str(version.id),
            model_used=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
        )
        return row

    def _fit_chunks_to_context(
        self,
        chunks: list[ChunkHydrationRow],
        *,
        model: str,
        style: SummaryType,
        topics: list[TopicContextRow],
        document_title: str,
    ) -> list[ChunkHydrationRow]:
        """Keep prefix of chunks (split last if needed) under the model context window."""
        context_window = model_context_window(self._settings, model)
        reserve = int(self._settings.summary_prompt_reserve_tokens) + int(
            self._settings.summary_max_output_tokens
        )
        max_source_tokens = max(512, context_window - reserve)

        # Approximate overhead from title + topic block without chunk bodies.
        overhead_system, overhead_user = build_summary_prompts(
            style=style,
            document_title=document_title,
            chunks=[],
            topics=topics if style == SummaryType.by_topic else None,
        )
        overhead = count_tokens(overhead_system) + count_tokens(overhead_user)
        remaining = max(256, max_source_tokens - overhead)

        selected: list[ChunkHydrationRow] = []
        used = 0
        for chunk in chunks:
            text = (chunk.content or "").strip()
            if not text:
                continue
            tokens = count_tokens(text)
            if used + tokens <= remaining:
                selected.append(chunk)
                used += tokens
                continue
            # Fit a truncated tail of this chunk if nothing selected yet, or partial fill.
            budget = remaining - used
            if budget < 64:
                break
            pieces = split_text_by_tokens(text, max_tokens=budget, overlap_ratio=0.0)
            if not pieces:
                break
            truncated = ChunkHydrationRow(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_version_id=chunk.document_version_id,
                workspace_id=chunk.workspace_id,
                content=pieces[0],
                title=chunk.title,
                page_number=chunk.page_number,
                section_index=chunk.section_index,
                section=chunk.section,
                chunk_index=chunk.chunk_index,
                heading_path=chunk.heading_path,
            )
            selected.append(truncated)
            break

        if not selected:
            raise SummaryServiceError(
                "content_too_large",
                "Document content exceeds model context window after budgeting",
                status_code=413,
            )
        return selected

    @staticmethod
    def _extract_summary_text(llm: StructuredLlmResult | Any) -> str:
        data = getattr(llm, "data", None)
        if isinstance(data, dict):
            for key in ("summary", "content", "text"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            # Fallback: first string value in the object.
            for value in data.values():
                if isinstance(value, str) and value.strip():
                    return value
        return ""
