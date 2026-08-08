# =============================================================================
# File: comparison_service.py
# Module/Service: Comparison Service (FR8)
# Layer: Service
# Purpose: Multi-document comparison (≥2 docs) with one structured LLM call (UC7).
# Responsibilities:
#   - Validate document_ids; use each document's current_version
#   - Prefer completed summaries; else top topic-ranked chunks
#   - Call strong-tier LLM once; persist comparisons + comparison_documents
#   - list / get / delete for HTTP API (presentation maps OpenAPI)
# Dependencies:
#   - DocumentRepository, RetrievalRepository, SummaryRepository, ComparisonRepository
#   - chat_llm adapter, model_tiering, count_tokens
# Public Exports:
#   - ComparisonService, ComparisonServiceError
# Database/Table: comparisons, comparison_documents, summaries, document_chunks,
#   topics, topic_chunks, documents, document_versions
# Related Modules: prompts, result_schemas, OpenAPI Comparison
# Important Notes:
#   - Complex query → prefer_strong=True (Claude Sonnet via Settings).
#   - Exactly one LLM call per comparison; never invent beyond provided context.
# =============================================================================

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.chat_llm import extract_structured_json_async, resolve_chat_llm
from app.adapters.llm_result import StructuredLlmResult
from app.ai.tokens import count_tokens
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.documents import Document, DocumentVersion
from app.models.enums import DocumentVersionStatus, SummaryStatus
from app.repositories.comparisons import ComparisonRepository, ComparisonWithDocuments
from app.repositories.documents import DocumentRepository
from app.repositories.retrieval import ChunkHydrationRow, RetrievalRepository
from app.repositories.summaries import SummaryRepository
from app.services.chat.model_tiering import (
    estimate_answer_cost_usd,
    model_context_window,
    select_answer_model,
)
from app.services.comparison.prompts import (
    DocumentCompareContext,
    build_comparison_prompts,
)
from app.services.comparison.result_schemas import (
    comparison_result_to_dict,
    parse_comparison_result,
)

logger = get_logger(__name__)


class ComparisonServiceError(Exception):
    """Domain error mapped to HTTP by the presentation layer."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ComparisonService:
    """Application service for FR8 Multi-document Analysis."""

    def __init__(
        self,
        *,
        settings: Settings,
        session: AsyncSession,
        documents: DocumentRepository,
        retrieval: RetrievalRepository,
        summaries: SummaryRepository,
        comparisons: ComparisonRepository,
        llm_call: Any | None = None,
    ) -> None:
        self._settings = settings
        self._session = session
        self._documents = documents
        self._retrieval = retrieval
        self._summaries = summaries
        self._comparisons = comparisons
        self._llm_call = llm_call

    # ------------------------------------------------------------------
    # HTTP API operations
    # ------------------------------------------------------------------

    async def create_comparison(
        self,
        *,
        workspace_id: uuid.UUID,
        document_ids: list[uuid.UUID],
        created_by: uuid.UUID,
        focus: str | None = None,
        title: str | None = None,
    ) -> ComparisonWithDocuments:
        """Compare ≥2 documents (current versions) and persist the result."""
        ordered_ids = self._normalize_document_ids(document_ids)
        focus_term = (focus or "").strip() or None

        resolved: list[tuple[Document, DocumentVersion]] = []
        for document_id in ordered_ids:
            document, version = await self._require_ready_current_version(
                workspace_id=workspace_id,
                document_id=document_id,
            )
            resolved.append((document, version))

        contexts: list[DocumentCompareContext] = []
        for document, version in resolved:
            ctx = await self._build_document_context(
                workspace_id=workspace_id,
                document=document,
                version=version,
                focus=focus_term,
            )
            if not self._context_has_content(ctx):
                raise ComparisonServiceError(
                    "insufficient_context",
                    f"Document {document.id} has no summary or chunks to compare",
                    status_code=409,
                )
            contexts.append(ctx)

        result_payload = await self._run_comparison_llm(
            contexts=contexts,
            focus=focus_term,
        )

        derived_title = title
        if derived_title is None:
            names = [((d.title or "").strip() or "untitled") for d, _ in resolved]
            derived_title = " vs ".join(names[:3])
            if len(names) > 3:
                derived_title = f"{derived_title} (+{len(names) - 3})"
            if focus_term:
                derived_title = f"{derived_title} — {focus_term}"

        outcome = await self._comparisons.create(
            workspace_id=workspace_id,
            created_by=created_by,
            document_ids=ordered_ids,
            result=result_payload,
            title=derived_title[:512] if derived_title else None,
        )
        await self._session.commit()

        logger.info(
            "comparison_created",
            comparison_id=str(outcome.comparison.id),
            workspace_id=str(workspace_id),
            document_count=len(ordered_ids),
            focus=focus_term,
        )
        return outcome

    async def list_comparisons(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> list[ComparisonWithDocuments]:
        return await self._comparisons.list_for_workspace(workspace_id=workspace_id)

    async def get_comparison(
        self,
        *,
        workspace_id: uuid.UUID,
        comparison_id: uuid.UUID,
    ) -> ComparisonWithDocuments:
        row = await self._comparisons.get(
            workspace_id=workspace_id,
            comparison_id=comparison_id,
        )
        if row is None:
            raise ComparisonServiceError(
                "not_found",
                "Comparison not found",
                status_code=404,
            )
        return row

    async def delete_comparison(
        self,
        *,
        workspace_id: uuid.UUID,
        comparison_id: uuid.UUID,
    ) -> None:
        row = await self._comparisons.get(
            workspace_id=workspace_id,
            comparison_id=comparison_id,
        )
        if row is None:
            raise ComparisonServiceError(
                "not_found",
                "Comparison not found",
                status_code=404,
            )
        await self._comparisons.delete(row.comparison)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _normalize_document_ids(self, document_ids: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(document_ids) < 2:
            raise ComparisonServiceError(
                "too_few_documents",
                "At least two document_ids are required",
                status_code=400,
            )
        seen: set[uuid.UUID] = set()
        ordered: list[uuid.UUID] = []
        for document_id in document_ids:
            if document_id in seen:
                continue
            seen.add(document_id)
            ordered.append(document_id)
        if len(ordered) < 2:
            raise ComparisonServiceError(
                "too_few_documents",
                "At least two distinct document_ids are required",
                status_code=400,
            )
        return ordered

    async def _require_ready_current_version(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> tuple[Document, DocumentVersion]:
        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            raise ComparisonServiceError(
                "not_found",
                f"Document {document_id} not found",
                status_code=404,
            )
        if document.current_version_id is None:
            raise ComparisonServiceError(
                "no_current_version",
                f"Document {document_id} has no current version",
                status_code=409,
            )
        version = await self._documents.get_version(
            workspace_id, document_id, document.current_version_id
        )
        if version is None:
            raise ComparisonServiceError(
                "no_current_version",
                f"Current version for document {document_id} not found",
                status_code=409,
            )
        if version.status != DocumentVersionStatus.ready:
            raise ComparisonServiceError(
                "version_not_ready",
                f"Document {document_id} current version status is "
                f"{version.status.value}; must be ready",
                status_code=409,
            )
        return document, version

    async def _build_document_context(
        self,
        *,
        workspace_id: uuid.UUID,
        document: Document,
        version: DocumentVersion,
        focus: str | None,
    ) -> DocumentCompareContext:
        summary = await self._summaries.get_latest_completed_for_version(
            workspace_id=workspace_id,
            document_id=document.id,
            source_version_id=version.id,
        )
        if summary is not None and summary.status == SummaryStatus.completed:
            text = self._summary_to_text(summary)
            if text.strip():
                return DocumentCompareContext(
                    document_id=str(document.id),
                    title=document.title or "",
                    source="summary",
                    summary_text=text,
                )

        limit = int(self._settings.comparison_top_chunks_per_document)
        chunks = await self._retrieval.list_top_chunks_by_topic(
            workspace_id,
            document.id,
            version_id=version.id,
            focus=focus,
            limit=limit,
        )
        return DocumentCompareContext(
            document_id=str(document.id),
            title=document.title or "",
            source="chunks",
            chunks=chunks,
        )

    @staticmethod
    def _summary_to_text(summary: Any) -> str:
        content = getattr(summary, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        sections = getattr(summary, "sections", None)
        if isinstance(sections, list) and sections:
            parts: list[str] = []
            for section in sections:
                if not isinstance(section, dict):
                    continue
                title = str(section.get("title") or "").strip()
                body = str(section.get("content") or "").strip()
                if title and body:
                    parts.append(f"## {title}\n{body}")
                elif body:
                    parts.append(body)
                elif title:
                    parts.append(f"## {title}")
            return "\n\n".join(parts)
        return ""

    @staticmethod
    def _context_has_content(ctx: DocumentCompareContext) -> bool:
        if ctx.source == "summary":
            return bool((ctx.summary_text or "").strip())
        return any((c.content or "").strip() for c in ctx.chunks)

    async def _run_comparison_llm(
        self,
        *,
        contexts: list[DocumentCompareContext],
        focus: str | None,
    ) -> dict[str, list[str]]:
        if resolve_chat_llm(self._settings) is None and self._llm_call is None:
            raise ComparisonServiceError(
                "llm_not_configured",
                "Chat LLM provider is not configured",
                status_code=503,
            )

        # Complex multi-document analysis → strong tier (Claude Sonnet via Settings).
        model = select_answer_model(
            self._settings,
            agent_triggered=False,
            prefer_strong=True,
        )
        budgeted = self._fit_contexts_to_window(
            contexts,
            model=model,
            focus=focus,
        )
        system, user = build_comparison_prompts(documents=budgeted, focus=focus)

        call_kwargs = {
            "system": system,
            "user": user,
            "model": model,
            "max_tokens": int(self._settings.comparison_max_output_tokens),
            "temperature": float(self._settings.chat_answer_temperature),
            "top_p": float(self._settings.chat_answer_top_p),
            "timeout_seconds": float(self._settings.comparison_timeout_seconds),
            "cost_estimator": lambda input_tokens, output_tokens: estimate_answer_cost_usd(
                self._settings,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            ),
        }

        started = time.perf_counter()
        try:
            if self._llm_call is not None:
                llm = await self._llm_call(**call_kwargs)
            else:
                llm = await extract_structured_json_async(
                    settings=self._settings,
                    **call_kwargs,
                )
        except Exception as exc:  # noqa: BLE001
            raise ComparisonServiceError(
                "llm_failed",
                "Comparison generation failed",
                status_code=502,
            ) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            parsed = parse_comparison_result(
                llm.data if isinstance(llm, StructuredLlmResult) else getattr(llm, "data", {})
            )
        except (ValidationError, ValueError, TypeError) as exc:
            raise ComparisonServiceError(
                "invalid_llm_payload",
                "LLM returned an invalid comparison JSON payload",
                status_code=502,
            ) from exc

        payload = comparison_result_to_dict(parsed)
        logger.info(
            "comparison_llm_ok",
            model=str(getattr(llm, "model", None) or model),
            latency_ms=latency_ms,
            similarities=len(payload["similarities"]),
            differences=len(payload["differences"]),
        )
        return payload

    def _fit_contexts_to_window(
        self,
        contexts: list[DocumentCompareContext],
        *,
        model: str,
        focus: str | None,
    ) -> list[DocumentCompareContext]:
        """Trim chunk-based contexts so the prompt fits the model window."""
        window = model_context_window(self._settings, model)
        reserve = int(self._settings.comparison_prompt_reserve_tokens)
        max_tokens = int(self._settings.comparison_max_output_tokens)
        budget = max(1_024, window - reserve - max_tokens)

        # Probe full prompt size; if within budget keep as-is.
        system, user = build_comparison_prompts(documents=contexts, focus=focus)
        if count_tokens(f"{system}\n{user}") <= budget:
            return contexts

        trimmed: list[DocumentCompareContext] = []
        for ctx in contexts:
            if ctx.source == "summary":
                text = (ctx.summary_text or "").strip()
                # Soft-trim overly long summaries by character budget per doc.
                per_doc_budget = max(512, budget // max(1, len(contexts)))
                # Approximate: ~4 chars/token.
                max_chars = per_doc_budget * 4
                if len(text) > max_chars:
                    text = text[:max_chars].rsplit(" ", 1)[0].strip()
                trimmed.append(
                    DocumentCompareContext(
                        document_id=ctx.document_id,
                        title=ctx.title,
                        source="summary",
                        summary_text=text,
                    )
                )
                continue

            kept: list[ChunkHydrationRow] = []
            running = 0
            per_doc_budget = max(512, budget // max(1, len(contexts)))
            for chunk in ctx.chunks:
                tokens = count_tokens(chunk.content or "")
                if kept and running + tokens > per_doc_budget:
                    break
                kept.append(chunk)
                running += tokens
            trimmed.append(
                DocumentCompareContext(
                    document_id=ctx.document_id,
                    title=ctx.title,
                    source="chunks",
                    chunks=kept or list(ctx.chunks[:1]),
                )
            )
        return trimmed
