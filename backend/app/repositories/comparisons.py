# =============================================================================
# File: comparisons.py
# Module/Service: Comparison Service (FR8)
# Layer: Repository
# Purpose: Async data access for multi-document comparisons (UC7).
# Responsibilities:
#   - Create processing Comparison + comparison_documents links
#   - Update completed/failed results; workspace-scoped list / get / delete
# Dependencies:
#   - SQLAlchemy AsyncSession; artifacts models
# Public Exports:
#   - ComparisonRepository, ComparisonWithDocuments
# Database/Table: comparisons, comparison_documents
# Related Modules: app.services.comparison.comparison_service
# Important Notes: Always filter by workspace_id for multi-tenant isolation.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifacts import Comparison, ComparisonDocument
from app.models.enums import ComparisonStatus


@dataclass(frozen=True, slots=True)
class ComparisonWithDocuments:
    """Comparison row plus document_ids in request order when preserved."""

    comparison: Comparison
    document_ids: list[uuid.UUID]


class ComparisonRepository:
    """Postgres data access for FR8 comparisons."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_processing(
        self,
        *,
        workspace_id: uuid.UUID,
        created_by: uuid.UUID,
        document_ids: list[uuid.UUID],
        focus: str | None = None,
        title: str | None = None,
    ) -> ComparisonWithDocuments:
        """Insert processing Comparison (result=null) and N-N document links."""
        row = Comparison(
            workspace_id=workspace_id,
            created_by=created_by,
            title=title,
            focus=focus,
            status=ComparisonStatus.processing,
            result=None,
        )
        self._session.add(row)
        await self._session.flush()

        ordered_ids = list(document_ids)
        for document_id in ordered_ids:
            self._session.add(
                ComparisonDocument(comparison_id=row.id, document_id=document_id)
            )
        await self._session.flush()
        return ComparisonWithDocuments(comparison=row, document_ids=ordered_ids)

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        created_by: uuid.UUID,
        document_ids: list[uuid.UUID],
        result: dict[str, Any],
        title: str | None = None,
        focus: str | None = None,
    ) -> ComparisonWithDocuments:
        """Insert a completed Comparison (sync / test helper)."""
        row = Comparison(
            workspace_id=workspace_id,
            created_by=created_by,
            title=title,
            focus=focus,
            status=ComparisonStatus.completed,
            result=result,
        )
        self._session.add(row)
        await self._session.flush()
        ordered_ids = list(document_ids)
        for document_id in ordered_ids:
            self._session.add(
                ComparisonDocument(comparison_id=row.id, document_id=document_id)
            )
        await self._session.flush()
        return ComparisonWithDocuments(comparison=row, document_ids=ordered_ids)

    async def get_by_id(self, comparison_id: uuid.UUID) -> Comparison | None:
        """Load by primary key (Celery worker — no workspace filter)."""
        return await self._session.get(Comparison, comparison_id)

    async def list_for_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[ComparisonWithDocuments]:
        stmt = (
            select(Comparison)
            .where(Comparison.workspace_id == workspace_id)
            .order_by(Comparison.created_at.desc())
            .offset(max(0, offset))
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = list((await self._session.execute(stmt)).scalars().all())
        return [await self._with_documents(row) for row in rows]

    async def count_for_workspace(self, *, workspace_id: uuid.UUID) -> int:
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(Comparison)
            .where(Comparison.workspace_id == workspace_id)
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def get(
        self,
        *,
        workspace_id: uuid.UUID,
        comparison_id: uuid.UUID,
    ) -> ComparisonWithDocuments | None:
        stmt = select(Comparison).where(
            Comparison.id == comparison_id,
            Comparison.workspace_id == workspace_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return await self._with_documents(row)

    async def update_generation_result(
        self,
        *,
        comparison_id: uuid.UUID,
        result: dict[str, Any],
        title: str | None = None,
    ) -> bool:
        """processing → completed. Returns False if missing or not processing."""
        values: dict[str, Any] = {
            "result": result,
            "status": ComparisonStatus.completed,
        }
        if title is not None:
            values["title"] = title
        stmt = (
            update(Comparison)
            .where(
                Comparison.id == comparison_id,
                Comparison.status == ComparisonStatus.processing,
            )
            .values(**values)
        )
        result_row = await self._session.execute(stmt)
        await self._session.flush()
        return bool(result_row.rowcount)

    async def mark_failed(self, *, comparison_id: uuid.UUID) -> bool:
        """processing → failed. result stays null."""
        stmt = (
            update(Comparison)
            .where(
                Comparison.id == comparison_id,
                Comparison.status == ComparisonStatus.processing,
            )
            .values(
                status=ComparisonStatus.failed,
                result=None,
            )
        )
        result_row = await self._session.execute(stmt)
        await self._session.flush()
        return bool(result_row.rowcount)

    async def delete(self, comparison: Comparison) -> None:
        await self._session.delete(comparison)
        await self._session.flush()

    async def list_document_ids(self, comparison_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(ComparisonDocument.document_id).where(
            ComparisonDocument.comparison_id == comparison_id
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def _with_documents(self, row: Comparison) -> ComparisonWithDocuments:
        document_ids = await self.list_document_ids(row.id)
        return ComparisonWithDocuments(comparison=row, document_ids=document_ids)

    async def unlink_all(self, comparison_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(ComparisonDocument).where(
                ComparisonDocument.comparison_id == comparison_id
            )
        )
        await self._session.flush()
