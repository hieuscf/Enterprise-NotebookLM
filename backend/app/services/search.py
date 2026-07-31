# =============================================================================
# File: search.py
# Module/Service: Search Service
# Layer: Service
# Purpose: Intelligent Search orchestration — Hybrid Retrieval + history (FR3/UC3).
# Responsibilities:
#   - Call HybridRetrievalService.retrieve() (sole retrieval path)
#   - Apply optional filters; persist search_history; map OpenAPI response
# Dependencies:
#   - HybridRetrievalService, SearchHistoryRepository, RetrievalRepository
# Public Exports:
#   - SearchService, SearchServiceError
# Database/Table: search_history, documents
# Related Modules: app.api.search, app.services.retrieval
# Important Notes: 0 LLM. Never reimplement Vector/BM25/Graph/Rerank here.
# =============================================================================

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.models.enums import FileType
from app.repositories.retrieval import RetrievalRepository
from app.repositories.search_history import SearchHistoryRepository
from app.schemas.search import (
    SearchFilters,
    SearchHistoryItemResponse,
    SearchRequest,
    SearchResultItem,
    SearchResultResponse,
)
from app.services.retrieval.exceptions import RetrievalUnavailableError
from app.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from app.services.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)

_OPENAPI_METHODS = frozenset({"vector", "bm25", "knowledge_graph", "rerank"})


class SearchServiceError(Exception):
    """Domain error for Search API with HTTP mapping hints."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class SearchService:
    """Search API business logic (UC3)."""

    def __init__(
        self,
        *,
        hybrid: HybridRetrievalService,
        history_repo: SearchHistoryRepository,
        retrieval_repo: RetrievalRepository,
    ) -> None:
        self._hybrid = hybrid
        self._history = history_repo
        self._retrieval_repo = retrieval_repo

    async def search(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        body: SearchRequest,
    ) -> SearchResultResponse:
        """Run hybrid retrieval, filter, persist history, return OpenAPI shape.

        Args:
            workspace_id: Tenant scope (already RBAC-checked).
            user_id: Authenticated user performing the search.
            body: Validated search request.

        Returns:
            ``SearchResultResponse`` matching OpenAPI.

        Raises:
            SearchServiceError: On retrieval unavailability or empty query.
        """
        query = (body.query_text or "").strip()
        if not query:
            raise SearchServiceError(
                "invalid_query",
                "query_text must not be empty",
                status_code=422,
            )

        filters_model = _normalize_filters(body.filters)
        filters_dict = (
            filters_model.model_dump(mode="json", exclude_none=True)
            if filters_model is not None
            else None
        )
        has_filters = bool(filters_dict)
        # Over-fetch when filtering so post-filter still has enough hits.
        fetch_k = body.top_k * 3 if has_filters else body.top_k
        fetch_k = max(fetch_k, body.top_k)

        try:
            result = await self._hybrid.retrieve(
                workspace_id,
                query,
                top_k=fetch_k,
            )
        except RetrievalUnavailableError as exc:
            logger.warning(
                "search_retrieval_unavailable",
                workspace_id=str(workspace_id),
                user_id=str(user_id),
                query=query[:200],
                error=str(exc),
            )
            raise SearchServiceError(
                "retrieval_unavailable",
                "Search backends are temporarily unavailable",
                status_code=503,
            ) from exc

        items = list(result.items)
        if has_filters and filters_model is not None:
            items = await self._apply_filters(workspace_id, items, filters_model)

        items = items[: body.top_k]
        for i, cand in enumerate(items, start=1):
            cand.rank = i

        # Persist history only after successful retrieval (even if 0 filtered hits).
        history_row = await self._history.create(
            workspace_id=workspace_id,
            user_id=user_id,
            query_text=query,
            filters=filters_dict,
            results_count=len(items),
        )

        response_items = [_to_result_item(c) for c in items if c.document_id is not None]
        # Drop candidates without document_id (cannot satisfy OpenAPI required field).
        for i, item in enumerate(response_items, start=1):
            item.rank = i

        logger.info(
            "search_completed",
            workspace_id=str(workspace_id),
            user_id=str(user_id),
            query_text=query[:200],
            filters=filters_dict,
            results_count=len(response_items),
            history_id=str(history_row.id),
            latency=result.latency_ms,
        )

        return SearchResultResponse(
            history_id=history_row.id,
            results_count=len(response_items),
            results=response_items,
        )

    async def list_history(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> list[SearchHistoryItemResponse]:
        """List search history for the current user only (newest first)."""
        rows, _total = await self._history.list_for_user(
            workspace_id=workspace_id,
            user_id=user_id,
            page=page,
            page_size=page_size,
        )
        return [_history_item(row) for row in rows]

    async def record_click(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        history_id: UUID,
        clicked_document_id: UUID,
    ) -> SearchHistoryItemResponse:
        """Set ``clicked_document_id`` on the caller's history row (idempotent).

        Args:
            workspace_id: Tenant scope.
            user_id: Authenticated owner of the history row.
            history_id: Target ``search_history.id``.
            clicked_document_id: Document the user opened from results.

        Returns:
            Updated ``SearchHistoryItemResponse``.

        Raises:
            SearchServiceError: 404 if history missing/not owned; 400 if document
                is not in the workspace.
        """
        meta = await self._retrieval_repo.documents_meta_by_ids(
            workspace_id,
            [clicked_document_id],
        )
        if clicked_document_id not in meta:
            raise SearchServiceError(
                "document_not_found",
                "Document not found in this workspace",
                status_code=404,
            )

        row = await self._history.set_clicked_document(
            workspace_id=workspace_id,
            user_id=user_id,
            history_id=history_id,
            document_id=clicked_document_id,
        )
        if row is None:
            raise SearchServiceError(
                "history_not_found",
                "Search history not found",
                status_code=404,
            )

        logger.info(
            "search_click_recorded",
            workspace_id=str(workspace_id),
            user_id=str(user_id),
            history_id=str(history_id),
            clicked_document_id=str(clicked_document_id),
        )
        return _history_item(row)

    async def _apply_filters(
        self,
        workspace_id: UUID,
        candidates: list[RetrievalCandidate],
        filters: SearchFilters,
    ) -> list[RetrievalCandidate]:
        doc_ids = [c.document_id for c in candidates if c.document_id is not None]
        meta = await self._retrieval_repo.documents_meta_by_ids(workspace_id, doc_ids)

        file_types = _parse_file_types(filters.file_type)
        date_from, date_to = _parse_date_window(filters)
        tags = [t.strip().lower() for t in (filters.tags or []) if t and t.strip()]
        if tags:
            # No tags table in schema v3 — filter is recorded in history but cannot
            # match document tags yet. Log once per request; do not invent tables.
            logger.info(
                "search_tags_filter_ignored",
                workspace_id=str(workspace_id),
                tags=tags,
                reason="document tags not in schema v3",
            )

        kept: list[RetrievalCandidate] = []
        for cand in candidates:
            if cand.document_id is None:
                continue
            row = meta.get(cand.document_id)
            if row is None:
                continue
            if file_types and row.file_type.value not in file_types:
                continue
            if date_from is not None and row.created_at < date_from:
                continue
            if date_to is not None and row.created_at > date_to:
                continue
            kept.append(cand)
        return kept


def _normalize_filters(
    raw: SearchFilters | dict[str, Any] | None,
) -> SearchFilters | None:
    if raw is None:
        return None
    if isinstance(raw, SearchFilters):
        data = raw.model_dump(exclude_none=True)
    else:
        data = {k: v for k, v in raw.items() if v is not None}
    if not data:
        return None
    return SearchFilters.model_validate(data)


def _parse_file_types(value: str | list[str] | None) -> set[str]:
    if value is None:
        return set()
    raw = value if isinstance(value, list) else [value]
    out: set[str] = set()
    for item in raw:
        token = str(item).strip().lower()
        if not token:
            continue
        try:
            out.add(FileType(token).value)
        except ValueError:
            continue
    return out


def _parse_date_window(filters: SearchFilters) -> tuple[datetime | None, datetime | None]:
    date_from = filters.date_from
    date_to = filters.date_to
    if filters.date_range and isinstance(filters.date_range, dict):
        raw_from = filters.date_range.get("from") or filters.date_range.get("start")
        raw_to = filters.date_range.get("to") or filters.date_range.get("end")
        if date_from is None and raw_from:
            date_from = _as_datetime(raw_from)
        if date_to is None and raw_to:
            date_to = _as_datetime(raw_to)
    return date_from, date_to


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _to_result_item(cand: RetrievalCandidate) -> SearchResultItem:
    method = cand.retrieval_method
    if method not in _OPENAPI_METHODS:
        # Prefer primary source if present; else rerank.
        sources = [m for m in cand.source_methods if m in _OPENAPI_METHODS]
        method = sources[0] if len(sources) == 1 else "rerank"
    assert cand.document_id is not None
    return SearchResultItem(
        chunk_id=cand.chunk_id,
        entity_id=cand.entity_id,
        document_id=cand.document_id,
        text_snippet=cand.text_snippet or "",
        retrieval_method=method,  # type: ignore[arg-type]
        score=float(cand.score if cand.score is not None else cand.raw_score),
        rank=int(cand.rank or 0),
    )


def _history_item(row: Any) -> SearchHistoryItemResponse:
    return SearchHistoryItemResponse(
        id=row.id,
        query_text=row.query_text,
        filters=row.filters,
        results_count=row.results_count,
        clicked_document_id=row.clicked_document_id,
        created_at=row.created_at,
    )
