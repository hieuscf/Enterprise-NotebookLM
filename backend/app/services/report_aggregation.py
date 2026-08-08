# =============================================================================
# File: report_aggregation.py
# Module/Service: Report Service (FR9) — Data Aggregation
# Layer: Service
# Purpose: Aggregate summary/extraction/comparison/chat_session sources into
#   format-agnostic report blocks for PDF/DOCX/Markdown renderers (UC8).
# Responsibilities:
#   - Validate every source_id belongs to the operating workspace_id
#   - Load source payloads via repositories (no direct ORM in this layer)
#   - Return sorted AggregatedReportBlock list ({order_index, source_type, title, content})
# Dependencies:
#   - SummaryRepository, ExtractionRepository, ComparisonRepository,
#     ChatSessionRepository, ChatMessageRepository, DocumentRepository
# Public Exports:
#   - ReportAggregationService, ReportAggregationError,
#     ReportItemInput, AggregatedReportBlock
# Database/Table: summaries, extractions, comparisons, chat_sessions, chat_messages,
#   documents (workspace join / titles)
# Related Modules: OpenAPI ReportItemInput; report renderers (Prompt 2–4)
# Important Notes:
#   - Does NOT generate PDF/DOCX/Markdown — Single Responsibility (aggregation only).
#   - Cross-workspace / missing source → 404 (do not leak existence across tenants).
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.chat import ChatMessage
from app.models.enums import ReportSourceType
from app.repositories.chat_messages import ChatMessageRepository
from app.repositories.chat_sessions import ChatSessionRepository
from app.repositories.comparisons import ComparisonRepository, ComparisonWithDocuments
from app.repositories.documents import DocumentRepository
from app.repositories.extractions import ExtractionRepository
from app.repositories.summaries import SummaryRepository


@dataclass(frozen=True, slots=True)
class ReportItemInput:
    """Mirrors OpenAPI ReportItemInput (aggregation input only)."""

    source_type: ReportSourceType
    source_id: uuid.UUID
    order_index: int


@dataclass(frozen=True, slots=True)
class AggregatedReportBlock:
    """Intermediate block for report renderers — format-agnostic."""

    order_index: int
    source_type: ReportSourceType
    title: str
    content: dict[str, Any]


class ReportAggregationError(Exception):
    """Domain error mapped to HTTP by the presentation layer (403/404)."""

    def __init__(self, code: str, message: str, *, status_code: int = 404) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ReportAggregationService:
    """Load and normalize report source items for a single workspace."""

    def __init__(
        self,
        *,
        summaries: SummaryRepository,
        extractions: ExtractionRepository,
        comparisons: ComparisonRepository,
        chat_sessions: ChatSessionRepository,
        chat_messages: ChatMessageRepository,
        documents: DocumentRepository,
    ) -> None:
        self._summaries = summaries
        self._extractions = extractions
        self._comparisons = comparisons
        self._chat_sessions = chat_sessions
        self._chat_messages = chat_messages
        self._documents = documents

    async def aggregate(
        self,
        *,
        workspace_id: uuid.UUID,
        items: list[ReportItemInput],
    ) -> list[AggregatedReportBlock]:
        """Fetch all items, validate workspace ownership, sort by order_index."""
        blocks: list[AggregatedReportBlock] = []
        for item in items:
            blocks.append(await self._aggregate_one(workspace_id=workspace_id, item=item))
        blocks.sort(key=lambda b: b.order_index)
        return blocks

    async def _aggregate_one(
        self,
        *,
        workspace_id: uuid.UUID,
        item: ReportItemInput,
    ) -> AggregatedReportBlock:
        source_type = self._coerce_source_type(item.source_type)

        if source_type is ReportSourceType.summary:
            return await self._from_summary(workspace_id, item)
        if source_type is ReportSourceType.extraction:
            return await self._from_extraction(workspace_id, item)
        if source_type is ReportSourceType.comparison:
            return await self._from_comparison(workspace_id, item)
        if source_type is ReportSourceType.chat_session:
            return await self._from_chat_session(workspace_id, item)

        raise ReportAggregationError(
            "invalid_source_type",
            f"Unsupported source_type: {item.source_type!r}",
            status_code=400,
        )

    def _coerce_source_type(self, value: ReportSourceType | str) -> ReportSourceType:
        if isinstance(value, ReportSourceType):
            return value
        try:
            return ReportSourceType(str(value))
        except ValueError as exc:
            raise ReportAggregationError(
                "invalid_source_type",
                f"Unsupported source_type: {value!r}",
                status_code=400,
            ) from exc

    async def _from_summary(
        self,
        workspace_id: uuid.UUID,
        item: ReportItemInput,
    ) -> AggregatedReportBlock:
        row = await self._summaries.get(
            workspace_id=workspace_id,
            summary_id=item.source_id,
        )
        if row is None:
            self._raise_source_unavailable(ReportSourceType.summary, item.source_id)

        style = row.type.value if hasattr(row.type, "value") else str(row.type)
        doc_title = await self._document_title(workspace_id, row.document_id)
        title = (
            f"Summary ({style}) — {doc_title}"
            if doc_title
            else f"Summary ({style})"
        )
        return AggregatedReportBlock(
            order_index=item.order_index,
            source_type=ReportSourceType.summary,
            title=title,
            content={
                "text": row.content,
                "style": style,
                "sections": row.sections,
            },
        )

    async def _from_extraction(
        self,
        workspace_id: uuid.UUID,
        item: ReportItemInput,
    ) -> AggregatedReportBlock:
        row = await self._extractions.get(
            workspace_id=workspace_id,
            extraction_id=item.source_id,
        )
        if row is None:
            self._raise_source_unavailable(ReportSourceType.extraction, item.source_id)

        extraction_type = (
            row.extraction_type.value
            if hasattr(row.extraction_type, "value")
            else str(row.extraction_type)
        )
        doc_title = await self._document_title(workspace_id, row.document_id)
        title = (
            f"Extraction ({extraction_type}) — {doc_title}"
            if doc_title
            else f"Extraction ({extraction_type})"
        )
        return AggregatedReportBlock(
            order_index=item.order_index,
            source_type=ReportSourceType.extraction,
            title=title,
            content={
                "result": row.result_json,
                "extraction_type": extraction_type,
            },
        )

    async def _from_comparison(
        self,
        workspace_id: uuid.UUID,
        item: ReportItemInput,
    ) -> AggregatedReportBlock:
        wrapped = await self._comparisons.get(
            workspace_id=workspace_id,
            comparison_id=item.source_id,
        )
        if wrapped is None:
            self._raise_source_unavailable(ReportSourceType.comparison, item.source_id)

        row = wrapped.comparison if isinstance(wrapped, ComparisonWithDocuments) else wrapped
        result = row.result if isinstance(row.result, dict) else {}
        similarities = list(result.get("similarities") or [])
        differences = list(result.get("differences") or [])
        title = (row.title or "").strip() or "Comparison"
        return AggregatedReportBlock(
            order_index=item.order_index,
            source_type=ReportSourceType.comparison,
            title=title,
            content={
                "similarities": similarities,
                "differences": differences,
            },
        )

    async def _from_chat_session(
        self,
        workspace_id: uuid.UUID,
        item: ReportItemInput,
    ) -> AggregatedReportBlock:
        session = await self._chat_sessions.get(
            session_id=item.source_id,
            workspace_id=workspace_id,
        )
        if session is None:
            self._raise_source_unavailable(ReportSourceType.chat_session, item.source_id)

        messages = await self._chat_messages.list_for_session(session_id=session.id)
        title = (session.title or "").strip() or "Chat session"
        return AggregatedReportBlock(
            order_index=item.order_index,
            source_type=ReportSourceType.chat_session,
            title=title,
            content={
                "messages": [self._message_payload(m) for m in messages],
            },
        )

    async def _document_title(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> str | None:
        document = await self._documents.get_document(workspace_id, document_id)
        if document is None:
            return None
        return document.title

    @staticmethod
    def _message_payload(message: ChatMessage) -> dict[str, Any]:
        role = message.role.value if hasattr(message.role, "value") else str(message.role)
        created_at = message.created_at
        created_at_str: str | None
        if isinstance(created_at, datetime):
            created_at_str = created_at.isoformat()
        else:
            created_at_str = str(created_at) if created_at is not None else None
        return {
            "role": role,
            "content": message.content,
            "created_at": created_at_str,
        }

    @staticmethod
    def _raise_source_unavailable(
        source_type: ReportSourceType,
        source_id: uuid.UUID,
    ) -> None:
        # 404 (not 403): do not reveal whether the id exists in another workspace.
        raise ReportAggregationError(
            "source_not_found",
            (
                f"{source_type.value} source {source_id} was not found in this "
                "workspace (missing or not accessible)"
            ),
            status_code=404,
        )
