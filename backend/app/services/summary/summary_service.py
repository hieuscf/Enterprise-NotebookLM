# =============================================================================
# File: summary_service.py
# Module/Service: Summary Service (FR6)
# Layer: Service
# Purpose: Async AI Summary request + generation for document versions (UC5).
# Responsibilities:
#   - request_summary: create processing row, commit, enqueue Celery (no LLM)
#   - process_summary: generate into existing row using persisted source_version_id
#   - list / get / delete for HTTP API
# Dependencies:
#   - DocumentRepository, RetrievalRepository, SummaryRepository
#   - chat_llm adapter, model_tiering, count_tokens
# Public Exports:
#   - SummaryService, SummaryServiceError
# Database/Table: summaries, documents, document_versions, document_chunks,
#   topics, topic_chunks
# Related Modules: app.services.summary.prompts, app.workers.summaries, OpenAPI
# Important Notes:
#   - API ``style`` maps to ORM/DB column ``type``.
#   - Celery MUST use source_version_id (never re-read current_version_id).
#   - HTTP path must not call the LLM; generation runs in process_summary only.
# =============================================================================

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.chat_llm import extract_structured_json_async, resolve_chat_llm
from app.adapters.llm_result import StructuredLlmResult
from app.ai.tokens import count_tokens, split_text_by_tokens
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.artifacts import Summary
from app.models.enums import (
    DocumentVersionStatus,
    SummaryStatus,
    SummaryStyle,
    SummaryType,
    TargetLanguage,
)
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

_STRONG_STYLES: frozenset[SummaryType] = frozenset(
    {SummaryType.detailed, SummaryType.by_topic}
)

EnqueueFn = Callable[[uuid.UUID], None]


class SummaryServiceError(Exception):
    """Domain error mapped to HTTP by the presentation layer."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class SummaryService:
    """Application service for FR6 AI Summary (request + generation)."""

    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        documents: DocumentRepository,
        retrieval: RetrievalRepository,
        summaries: SummaryRepository,
        llm_call: Any | None = None,
        enqueue: bool = True,
        enqueue_fn: EnqueueFn | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._documents = documents
        self._retrieval = retrieval
        self._summaries = summaries
        self._llm_call = llm_call
        self._enqueue = enqueue
        self._enqueue_fn = enqueue_fn

    # ------------------------------------------------------------------
    # HTTP API operations
    # ------------------------------------------------------------------

    async def request_summary(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        style: SummaryStyle,
        created_by: uuid.UUID,
        target_language: TargetLanguage = TargetLanguage.vi,
    ) -> Summary:
        """Create processing Summary, commit, enqueue Celery — no LLM in-request."""
        summary_type = SummaryType(style)
        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise SummaryServiceError("not_found", "Document not found", status_code=404)
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

        # Capture authoritative source version BEFORE enqueue / any later version flip.
        source_version_id = version.id
        row = await self._summaries.create_processing(
            document_id=document.id,
            created_by=created_by,
            source_version_id=source_version_id,
            type_=summary_type,
            target_language=target_language,
        )
        # Commit before enqueue so the worker can see the row (documents pattern).
        await self._session.commit()

        try:
            self._enqueue_summary(row.id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("summary_enqueue_failed", summary_id=str(row.id))
            await self._summaries.mark_failed(summary_id=row.id)
            await self._session.commit()
            raise SummaryServiceError(
                "enqueue_failed",
                "Failed to schedule summary generation",
                status_code=503,
            ) from exc

        # Refresh after commit so response reflects persisted processing state.
        refreshed = await self._summaries.get_by_id(row.id)
        return refreshed or row

    async def list_summaries(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[Summary]:
        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise SummaryServiceError("not_found", "Document not found", status_code=404)
        return await self._summaries.list_for_document(
            workspace_id=workspace_id,
            document_id=document_id,
        )

    async def get_summary(
        self,
        *,
        workspace_id: uuid.UUID,
        summary_id: uuid.UUID,
    ) -> Summary:
        row = await self._summaries.get(workspace_id=workspace_id, summary_id=summary_id)
        if row is None:
            raise SummaryServiceError("not_found", "Summary not found", status_code=404)
        return row

    async def delete_summary(
        self,
        *,
        workspace_id: uuid.UUID,
        summary_id: uuid.UUID,
    ) -> None:
        row = await self._summaries.get(workspace_id=workspace_id, summary_id=summary_id)
        if row is None:
            raise SummaryServiceError("not_found", "Summary not found", status_code=404)
        await self._summaries.delete(row)

    # ------------------------------------------------------------------
    # Celery / generation
    # ------------------------------------------------------------------

    async def process_summary(self, summary_id: uuid.UUID) -> Summary | None:
        """Generate into an existing processing Summary using source_version_id.

        Idempotent:
          - missing / deleted → None (exit safely)
          - not processing → return row unchanged (no regenerate)
        """
        row = await self._summaries.get_by_id(summary_id)
        if row is None:
            logger.info("summary_process_missing", summary_id=str(summary_id))
            return None
        if row.status != SummaryStatus.processing:
            logger.info(
                "summary_process_skip_status",
                summary_id=str(summary_id),
                status=row.status.value,
            )
            return row

        document = await self._documents.get_document_by_id(row.document_id)
        if document is None:
            await self._summaries.mark_failed(summary_id=row.id)
            return await self._summaries.get_by_id(row.id)

        workspace_id = document.workspace_id
        version = await self._documents.get_version(
            workspace_id, row.document_id, row.source_version_id
        )
        if version is None:
            await self._fail_safe(row.id, "source_version_missing")
            return await self._summaries.get_by_id(row.id)

        try:
            result = await self._generate_content(
                workspace_id=workspace_id,
                document_id=row.document_id,
                document_title=document.title,
                source_version_id=row.source_version_id,
                style=row.type,
                target_language=row.target_language,
            )
        except SummaryServiceError as exc:
            logger.warning(
                "summary_generation_failed",
                summary_id=str(row.id),
                code=exc.code,
            )
            await self._summaries.mark_failed(summary_id=row.id)
            return await self._summaries.get_by_id(row.id)
        except Exception:  # noqa: BLE001
            logger.exception("summary_generation_unexpected", summary_id=str(row.id))
            await self._summaries.mark_failed(summary_id=row.id)
            return await self._summaries.get_by_id(row.id)

        updated = await self._summaries.update_generation_result(
            summary_id=row.id,
            content=result["content"],
            sections=result.get("sections"),
            model_used=result["model_used"],
            prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"],
            cost_usd=result["cost_usd"],
            latency_ms=result["latency_ms"],
        )
        if not updated:
            # Race: deleted or status flipped while generating.
            logger.info("summary_process_race_skip", summary_id=str(row.id))
            return await self._summaries.get_by_id(row.id)

        final = await self._summaries.get_by_id(row.id)
        logger.info(
            "summary_generated",
            summary_id=str(row.id),
            source_version_id=str(row.source_version_id),
            style=row.type.value,
            model_used=result["model_used"],
        )
        return final

    async def generate_summary(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        style: SummaryStyle,
        created_by: uuid.UUID,
        target_language: TargetLanguage = TargetLanguage.vi,
    ) -> Summary:
        """In-process create+process (tests / sync callers). Still one Summary row."""
        summary_type = SummaryType(style)
        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise SummaryServiceError("not_found", "Document not found", status_code=404)
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
        row = await self._summaries.create_processing(
            document_id=document.id,
            created_by=created_by,
            source_version_id=version.id,
            type_=summary_type,
            target_language=target_language,
        )
        await self._session.flush()
        final = await self.process_summary(row.id)
        if final is None or final.status != SummaryStatus.completed:
            raise SummaryServiceError(
                "llm_failed",
                "Summary generation failed",
                status_code=502,
            )
        return final

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enqueue_summary(self, summary_id: uuid.UUID) -> None:
        if not self._enqueue:
            return
        if self._enqueue_fn is not None:
            self._enqueue_fn(summary_id)
            return
        from app.workers.summaries import generate_summary as generate_summary_task

        generate_summary_task.delay(str(summary_id))

    async def _fail_safe(self, summary_id: uuid.UUID, reason: str) -> None:
        logger.warning("summary_mark_failed", summary_id=str(summary_id), reason=reason)
        await self._summaries.mark_failed(summary_id=summary_id)

    async def _generate_content(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        document_title: str,
        source_version_id: uuid.UUID,
        style: SummaryType,
        target_language: TargetLanguage = TargetLanguage.vi,
    ) -> dict[str, Any]:
        """Run LLM generation for a pinned source_version_id (no Summary insert)."""
        chunks = await self._retrieval.list_chunks_for_document(
            workspace_id,
            document_id,
            version_id=source_version_id,
        )
        if not chunks:
            raise SummaryServiceError(
                "no_chunks",
                "Source document version has no chunks to summarize",
                status_code=409,
            )

        topics: list[TopicContextRow] = []
        if style == SummaryType.by_topic:
            topics = await self._summaries.list_topics_for_version(
                workspace_id=workspace_id,
                document_version_id=source_version_id,
            )

        if resolve_chat_llm(self._settings) is None and self._llm_call is None:
            raise SummaryServiceError(
                "llm_not_configured",
                "Chat LLM provider is not configured",
                status_code=503,
            )

        prefer_strong = style in _STRONG_STYLES
        model = select_answer_model(
            self._settings,
            agent_triggered=False,
            prefer_strong=prefer_strong,
        )
        budgeted_chunks = self._fit_chunks_to_context(
            chunks,
            model=model,
            style=style,
            topics=topics,
            document_title=document_title,
            target_language=target_language,
        )
        system, user = build_summary_prompts(
            style=style,
            document_title=document_title,
            chunks=budgeted_chunks,
            topics=topics if style == SummaryType.by_topic else None,
            target_language=target_language,
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
        except Exception as exc:  # noqa: BLE001
            raise SummaryServiceError(
                "llm_failed",
                "Summary generation failed",
                status_code=502,
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        sections = (
            self._extract_sections(llm, topics=topics, target_language=target_language)
            if style == SummaryType.by_topic
            else None
        )
        content = self._extract_summary_text(llm)
        if not content.strip() and sections:
            content = "\n\n".join(
                f"## {s['title']}\n{s['content']}".strip() for s in sections
            )
        if not content.strip() and not sections:
            raise SummaryServiceError(
                "empty_summary",
                "LLM returned an empty summary",
                status_code=502,
            )
        if style == SummaryType.by_topic and not sections:
            raise SummaryServiceError(
                "empty_summary",
                "LLM returned no topic sections",
                status_code=502,
            )

        return {
            "content": (content.strip() if content and content.strip() else "")
            or (
                "\n\n".join(f"## {s['title']}\n{s['content']}".strip() for s in sections)
                if sections
                else ""
            ),
            "sections": sections,
            "model_used": str(getattr(llm, "model", None) or model),
            "prompt_tokens": int(getattr(llm, "input_tokens", 0) or 0),
            "completion_tokens": int(getattr(llm, "output_tokens", 0) or 0),
            "cost_usd": Decimal(
                str(round(float(getattr(llm, "estimated_cost_usd", 0.0) or 0.0), 6))
            ),
            "latency_ms": latency_ms,
        }

    def _fit_chunks_to_context(
        self,
        chunks: list[ChunkHydrationRow],
        *,
        model: str,
        style: SummaryType,
        topics: list[TopicContextRow],
        document_title: str,
        target_language: TargetLanguage = TargetLanguage.vi,
    ) -> list[ChunkHydrationRow]:
        context_window = model_context_window(self._settings, model)
        reserve = int(self._settings.summary_prompt_reserve_tokens) + int(
            self._settings.summary_max_output_tokens
        )
        max_source_tokens = max(512, context_window - reserve)

        overhead_system, overhead_user = build_summary_prompts(
            style=style,
            document_title=document_title,
            chunks=[],
            topics=topics if style == SummaryType.by_topic else None,
            target_language=target_language,
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
            budget = remaining - used
            if budget < 64:
                break
            pieces = split_text_by_tokens(text, max_tokens=budget, overlap_ratio=0.0)
            if not pieces:
                break
            selected.append(
                ChunkHydrationRow(
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
            )
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
            for value in data.values():
                if isinstance(value, str) and value.strip():
                    return value
        return ""

    @staticmethod
    def _extract_sections(
        llm: StructuredLlmResult | Any,
        *,
        topics: list[TopicContextRow],
        target_language: TargetLanguage = TargetLanguage.vi,
    ) -> list[dict[str, Any]] | None:
        """Normalize backend-produced topic sections (no FE heuristics)."""
        data = getattr(llm, "data", None)
        if not isinstance(data, dict):
            return None
        raw = data.get("sections")
        if not isinstance(raw, list) or not raw:
            return None
        known_ids = {str(t.topic_id): t for t in topics}
        fallback_title = (
            "Topic" if target_language == TargetLanguage.en else "Chủ đề"
        )
        out: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            content = str(item.get("content") or item.get("summary") or "").strip()
            if not title and not content:
                continue
            topic_id_raw = item.get("topic_id")
            topic_id: str | None = None
            if topic_id_raw is not None and str(topic_id_raw).strip():
                key = str(topic_id_raw).strip()
                if key in known_ids:
                    topic_id = key
                    if not title:
                        title = known_ids[key].name
            out.append(
                {
                    "topic_id": topic_id,
                    "title": title or fallback_title,
                    "content": content,
                }
            )
        return out or None
