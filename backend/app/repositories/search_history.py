# =============================================================================
# File: search_history.py
# Module/Service: Search Service
# Layer: Repository
# Purpose: Async data access for search_history (FR3 / UC3).
# Responsibilities:
#   - Insert search rows; list current user's history newest-first with pagination
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.query.SearchHistory
# Public Exports:
#   - SearchHistoryRepository
# Database/Table: search_history
# Related Modules: app.services.search, database-design §7
# Important Notes: Always filter by workspace_id AND user_id for list/get.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.query import SearchHistory


class SearchHistoryRepository:
    """CRUD helpers for ``search_history`` scoped by workspace + user."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        query_text: str,
        filters: dict[str, Any] | None,
        results_count: int,
    ) -> SearchHistory:
        row = SearchHistory(
            workspace_id=workspace_id,
            user_id=user_id,
            query_text=query_text,
            filters=filters,
            results_count=results_count,
            clicked_document_id=None,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_user(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SearchHistory], int]:
        filters = [
            SearchHistory.workspace_id == workspace_id,
            SearchHistory.user_id == user_id,
        ]
        count_stmt = select(func.count()).select_from(SearchHistory).where(*filters)
        total = int((await self._session.execute(count_stmt)).scalar_one())

        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        list_stmt = (
            select(SearchHistory)
            .where(*filters)
            .order_by(SearchHistory.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await self._session.execute(list_stmt)).scalars().all())
        return rows, total

    async def get_for_user(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        history_id: uuid.UUID,
    ) -> SearchHistory | None:
        stmt = select(SearchHistory).where(
            SearchHistory.id == history_id,
            SearchHistory.workspace_id == workspace_id,
            SearchHistory.user_id == user_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def set_clicked_document(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        history_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> SearchHistory | None:
        """Update click target on an owned history row (idempotent)."""
        row = await self.get_for_user(
            workspace_id=workspace_id,
            user_id=user_id,
            history_id=history_id,
        )
        if row is None:
            return None
        row.clicked_document_id = document_id
        await self._session.flush()
        return row
