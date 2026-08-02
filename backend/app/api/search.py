# =============================================================================
# File: search.py
# Module/Service: Search Service
# Layer: Presentation
# Purpose: FastAPI routes for Intelligent Search + history (FR3 / UC3).
# Responsibilities:
#   - POST /workspaces/{id}/search — Hybrid Retrieval + search_history write
#   - GET /workspaces/{id}/search/history — current user history (paginated)
#   - PATCH .../search/history/{historyId} — record clicked_document_id (C+A)
# Dependencies:
#   - require_workspace_member_rl, SearchService, HybridRetrievalService factory
# Public Exports:
#   - router
# Database/Table: search_history
# Related Modules: docs/Enterprise_notebooklm_openapi.yaml §SEARCH
# Important Notes: Click PATCH is idempotent; only history owner may update.
# =============================================================================

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.elasticsearch_bm25 import get_elasticsearch_bm25
from app.adapters.neo4j_graph import get_neo4j_graph
from app.adapters.qdrant_store import get_qdrant_store
from app.core.config import get_settings
from app.db.session import get_db_session
from app.dependencies.rate_limit import require_workspace_member_rl
from app.dependencies.rbac import WorkspaceAccess
from app.repositories.retrieval import RetrievalRepository
from app.repositories.search_history import SearchHistoryRepository
from app.schemas.common import ErrorResponse
from app.schemas.search import (
    SearchHistoryClickRequest,
    SearchHistoryItemResponse,
    SearchRequest,
    SearchResultResponse,
)
from app.services.retrieval.bm25_search import Bm25Search
from app.services.retrieval.graph_search import GraphSearch
from app.services.retrieval.hybrid_retrieval_service import HybridRetrievalService
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.vector_search import VectorSearch
from app.services.search import SearchService, SearchServiceError

router = APIRouter(prefix="/workspaces", tags=["Search"])


def get_search_service(
    session: AsyncSession = Depends(get_db_session),
) -> SearchService:
    """Wire Hybrid Retrieval + history repos for the Search Service."""
    settings = get_settings()
    retrieval_repo = RetrievalRepository(session)
    hybrid = HybridRetrievalService(
        settings=settings,
        vector_search=VectorSearch(
            settings=settings,
            qdrant=get_qdrant_store(),
            repo=retrieval_repo,
        ),
        bm25_search=Bm25Search(
            settings=settings,
            elasticsearch=get_elasticsearch_bm25(),
            repo=retrieval_repo,
        ),
        graph_search=GraphSearch(
            settings=settings,
            neo4j=get_neo4j_graph(),
            repo=retrieval_repo,
        ),
        reranker=Reranker(settings),
    )
    return SearchService(
        hybrid=hybrid,
        history_repo=SearchHistoryRepository(session),
        retrieval_repo=retrieval_repo,
        settings=settings,
    )


def _http_error(exc: SearchServiceError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail=ErrorResponse(code=exc.code, message=exc.message).model_dump(),
    )


@router.post(
    "/{workspaceId}/search",
    response_model=SearchResultResponse,
    summary="Tìm kiếm ngữ nghĩa (Hybrid Retrieval Vector+BM25+KG, ghi search_history)",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)
async def search_workspace(
    body: SearchRequest,
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: SearchService = Depends(get_search_service),
) -> SearchResultResponse:
    """Semantic search within a workspace; writes one ``search_history`` row."""
    try:
        return await service.search(
            workspace_id=access.workspace_id,
            user_id=access.user_id,
            body=body,
        )
    except SearchServiceError as exc:
        raise _http_error(exc) from exc


@router.get(
    "/{workspaceId}/search/history",
    response_model=list[SearchHistoryItemResponse],
    summary="Lịch sử tìm kiếm của user hiện tại trong Workspace",
    responses={status.HTTP_403_FORBIDDEN: {"model": ErrorResponse}},
)
async def list_search_history(
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: SearchService = Depends(get_search_service),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> list[SearchHistoryItemResponse]:
    """Return the caller's search history only (newest first)."""
    return await service.list_history(
        workspace_id=access.workspace_id,
        user_id=access.user_id,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/{workspaceId}/search/history/{historyId}",
    response_model=SearchHistoryItemResponse,
    summary="Ghi nhận tài liệu được click từ một lần tìm kiếm (clicked_document_id)",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
    },
)
async def patch_search_history_click(
    body: SearchHistoryClickRequest,
    historyId: uuid.UUID = Path(..., description="search_history UUID"),
    access: WorkspaceAccess = Depends(require_workspace_member_rl),
    service: SearchService = Depends(get_search_service),
) -> SearchHistoryItemResponse:
    """Idempotent update of ``clicked_document_id`` for the caller's history row."""
    try:
        return await service.record_click(
            workspace_id=access.workspace_id,
            user_id=access.user_id,
            history_id=historyId,
            clicked_document_id=body.clicked_document_id,
        )
    except SearchServiceError as exc:
        raise _http_error(exc) from exc
