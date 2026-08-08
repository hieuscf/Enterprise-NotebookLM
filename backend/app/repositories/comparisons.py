# =============================================================================
# File: comparisons.py
# Module/Service: Comparison Service (FR8)
# Layer: Repository
# Purpose: Async data access for multi-document comparisons (UC7).
# Responsibilities:
#   - Create Comparison + comparison_documents links
#   - Workspace-scoped list / get / delete
# Dependencies:
#   - SQLAlchemy AsyncSession; artifacts / documents models
# Public Exports:
#   - ComparisonRepository, ComparisonWithDocuments
# Database/Table: comparisons, comparison_documents, documents
# Related Modules: app.services.comparison.comparison_service
# Important Notes: Always filter by workspace_id for multi-tenant isolation.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifacts import Comparison, ComparisonDocument


@dataclass(frozen=True, slots=True)
class ComparisonWithDocuments:
    """Comparison row plus ordered document_ids from the join table."""

    comparison: Comparison
    document_ids: list[uuid.UUID]


class ComparisonRepository:
    """Postgres data access for FR8 comparisons."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        created_by: uuid.UUID,
        document_ids: list[uuid.UUID],
        result: dict[str, Any],
        title: str | None = None,
    ) -> ComparisonWithDocuments:
        """Insert Comparison and N-N links in ``comparison_documents``."""
        row = Comparison(
            workspace_id=workspace_id,
            created_by=created_by,
            title=title,
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

    async def list_for_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
    ) -> list[ComparisonWithDocuments]:
        stmt = (
            select(Comparison)
            .where(Comparison.workspace_id == workspace_id)
            .order_by(Comparison.created_at.desc())
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return [await self._with_documents(row) for row in rows]

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

    async def delete(self, comparison: Comparison) -> None:
        await self._session.delete(comparison)
        await self._session.flush()

    async def list_document_ids(self, comparison_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = (
            select(ComparisonDocument.document_id)
            .where(ComparisonDocument.comparison_id == comparison_id)
            .order_by(ComparisonDocument.document_id.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def _with_documents(self, row: Comparison) -> ComparisonWithDocuments:
        # Preserve insertion order when available via a second ordered query by PK
        # is not meaningful; return ids sorted for stable API responses.
        document_ids = await self.list_document_ids(row.id)
        return ComparisonWithDocuments(comparison=row, document_ids=document_ids)

    async def unlink_all(self, comparison_id: uuid.UUID) -> None:
        """Remove join rows (CASCADE on comparison delete also covers this)."""
        await self._session.execute(
            delete(ComparisonDocument).where(
                ComparisonDocument.comparison_id == comparison_id
            )
        )
        await self._session.flush()
