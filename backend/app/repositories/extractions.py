# =============================================================================
# File: extractions.py
# Module/Service: Extraction Service (FR7)
# Layer: Repository
# Purpose: Async data access for extractions + version-scoped graph entities.
# Responsibilities:
#   - Create / get / list / delete Extraction rows
#   - List Entity rows for a document_version (entity reuse path)
# Dependencies:
#   - SQLAlchemy AsyncSession; artifacts / knowledge / documents models
# Public Exports:
#   - ExtractionRepository, EntityReuseRow
# Database/Table: extractions, entities, documents
# Related Modules: app.services.extraction.extraction_service
# Important Notes:
#   - Always filter by workspace_id for HTTP multi-tenant isolation.
#   - Entities are version-scoped via Entity.source_version_id (not document_id).
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifacts import Extraction
from app.models.documents import Document
from app.models.enums import ExtractionOutputFormat, ExtractionType
from app.models.knowledge import Entity


@dataclass(frozen=True, slots=True)
class EntityReuseRow:
    """Graph entity fields projected into Extraction result.entities."""

    id: uuid.UUID
    name: str
    type: str
    description: str | None


class ExtractionRepository:
    """Postgres data access for FR7 extractions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        document_id: uuid.UUID,
        created_by: uuid.UUID,
        source_version_id: uuid.UUID,
        extraction_type: ExtractionType,
        output_format: ExtractionOutputFormat,
        result_json: dict[str, Any],
        model_used: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: Decimal,
        latency_ms: int | None,
    ) -> Extraction:
        row = Extraction(
            document_id=document_id,
            created_by=created_by,
            source_version_id=source_version_id,
            extraction_type=extraction_type,
            output_format=output_format,
            result_json=result_json,
            model_used=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(
        self,
        *,
        workspace_id: uuid.UUID,
        extraction_id: uuid.UUID,
    ) -> Extraction | None:
        stmt = (
            select(Extraction)
            .join(Document, Document.id == Extraction.document_id)
            .where(
                Extraction.id == extraction_id,
                Document.workspace_id == workspace_id,
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, extraction_id: uuid.UUID) -> Extraction | None:
        return await self._session.get(Extraction, extraction_id)

    async def list_for_document(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[Extraction]:
        stmt = (
            select(Extraction)
            .join(Document, Document.id == Extraction.document_id)
            .where(
                Extraction.document_id == document_id,
                Document.workspace_id == workspace_id,
            )
            .order_by(Extraction.created_at.desc())
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def delete(self, row: Extraction) -> None:
        await self._session.delete(row)

    async def list_entities_for_version(
        self,
        *,
        workspace_id: uuid.UUID,
        source_version_id: uuid.UUID,
    ) -> list[EntityReuseRow]:
        """Entities produced by Graph Extraction for exactly one document_version."""
        stmt = (
            select(Entity)
            .where(
                Entity.workspace_id == workspace_id,
                Entity.source_version_id == source_version_id,
            )
            .order_by(Entity.name.asc(), Entity.id.asc())
        )
        rows = list((await self._session.execute(stmt)).scalars().all())
        return [
            EntityReuseRow(
                id=e.id,
                name=e.name,
                type=e.type,
                description=e.description,
            )
            for e in rows
        ]
