# =============================================================================
# File: retrieval.py
# Module/Service: Search Service / Hybrid Retrieval
# Layer: Repository
# Purpose: Async Postgres lookups to hydrate chunks/documents for retrieval (FR3).
# Responsibilities:
#   - Resolve chunk content + document_id scoped by workspace_id
#   - Metadata queries (document list/count/stats) for Metadata Retrieval
#   - Topic-ranked top chunks for multi-document comparison fallback (FR8)
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.documents, app.models.knowledge
# Public Exports:
#   - ChunkHydrationRow, MetadataDocumentRow, RetrievalRepository
# Database/Table: document_chunks, document_versions, documents, entities,
#   topics, topic_chunks, users
# Related Modules: app.services.retrieval.*, app.services.comparison
# Important Notes: Always filter by workspace_id — multi-tenant isolation.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, and_, case, desc, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import Document, DocumentVersion
from app.models.enums import ChunkLayoutType, FileType
from app.models.knowledge import DocumentChunk, Entity, Topic, TopicChunk


def _to_hydration_row(
    chunk: DocumentChunk,
    document: Document,
    version: DocumentVersion,
) -> ChunkHydrationRow:
    """Map a joined chunk/document/version row to ``ChunkHydrationRow``."""
    return ChunkHydrationRow(
        chunk_id=chunk.id,
        document_id=document.id,
        document_version_id=version.id,
        workspace_id=document.workspace_id,
        content=chunk.content or "",
        title=document.title,
        page_number=chunk.page_number,
        section_index=chunk.section_index,
        section=chunk.section,
        chunk_index=chunk.chunk_index,
        heading_path=chunk.heading_path,
        layout_type=chunk.layout_type,
        parent_chunk_id=chunk.parent_chunk_id,
        depth=chunk.depth,
    )


@dataclass(frozen=True, slots=True)
class ChunkHydrationRow:
    """Chunk fields needed to build a RetrievalCandidate."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_version_id: uuid.UUID
    workspace_id: uuid.UUID
    content: str
    title: str | None = None
    page_number: int | None = None
    section_index: int | None = None
    section: str | None = None
    chunk_index: int | None = None
    heading_path: str | None = None
    layout_type: ChunkLayoutType | None = None
    parent_chunk_id: uuid.UUID | None = None
    depth: int | None = None


@dataclass(frozen=True, slots=True)
class MetadataDocumentRow:
    """Document metadata row for Metadata Retrieval / Query Router."""

    document_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    file_type: FileType
    created_at: datetime
    updated_at: datetime
    uploaded_by: uuid.UUID | None
    version_number: int | None
    status: str | None


class RetrievalRepository:
    """Postgres data access for Hybrid Retrieval hydration + metadata queries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def hydrate_chunks(
        self,
        workspace_id: uuid.UUID,
        chunk_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, ChunkHydrationRow]:
        """Load chunk content + document_id for ids belonging to ``workspace_id``."""
        if not chunk_ids:
            return {}
        stmt: Select[tuple[DocumentChunk, Document, DocumentVersion]] = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.workspace_id == workspace_id,
                DocumentChunk.id.in_(chunk_ids),
            )
        )
        rows = (await self._session.execute(stmt)).all()
        out: dict[uuid.UUID, ChunkHydrationRow] = {}
        for chunk, document, version in rows:
            out[chunk.id] = _to_hydration_row(chunk, document, version)
        return out

    async def fetch_sibling_chunks(
        self,
        workspace_id: uuid.UUID,
        seeds: list[tuple[uuid.UUID, int]],
        *,
        window: int = 1,
        exclude_chunk_ids: set[uuid.UUID] | None = None,
        max_total: int = 20,
    ) -> list[ChunkHydrationRow]:
        """Bounded neighbor expansion: chunks within ``window`` of each seed.

        Args:
            seeds: ``(document_version_id, chunk_index)`` pairs for chunks
                already retrieved — the anchor to expand around.
            window: How many chunks before/after each seed to include.
            exclude_chunk_ids: Chunk ids already present in the retrieval set
                (skip re-fetching them as "new" neighbors).
            max_total: Hard cap — never blindly expand to a whole document.

        Returns:
            Deduplicated sibling rows ordered by ``(document_version_id, chunk_index)``.
        """
        if not seeds or max_total <= 0:
            return []
        exclude = exclude_chunk_ids or set()
        window = max(0, window)

        version_ranges: dict[uuid.UUID, set[int]] = {}
        for version_id, chunk_index in seeds:
            if chunk_index is None:
                continue
            lo = max(0, int(chunk_index) - window)
            hi = int(chunk_index) + window
            version_ranges.setdefault(version_id, set()).update(range(lo, hi + 1))
        if not version_ranges:
            return []

        conditions = [
            and_(
                DocumentChunk.document_version_id == version_id,
                DocumentChunk.chunk_index.in_(indices),
            )
            for version_id, indices in version_ranges.items()
        ]
        stmt = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(Document.workspace_id == workspace_id, or_(*conditions))
            .order_by(
                DocumentChunk.document_version_id.asc(),
                DocumentChunk.chunk_index.asc(),
            )
            .limit(max(1, max_total) + len(exclude))
        )
        rows = (await self._session.execute(stmt)).all()
        out: list[ChunkHydrationRow] = []
        for chunk, document, version in rows:
            if chunk.id in exclude:
                continue
            out.append(_to_hydration_row(chunk, document, version))
            if len(out) >= max_total:
                break
        return out

    async def fetch_representative_chunks(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
        *,
        limit: int = 6,
    ) -> list[ChunkHydrationRow]:
        """Deterministic representative-coverage chunks for global questions (§7).

        Picks the document's first chunk (title/intro), evenly-spaced heading
        chunks across the document, and the last chunk — bounded by ``limit``.
        No LLM / no embedding; pure ``chunk_index`` + ``layout_type`` heuristic.
        """
        if limit <= 0:
            return []
        stmt = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.workspace_id == workspace_id,
                DocumentChunk.document_version_id == document_version_id,
            )
            .order_by(DocumentChunk.chunk_index.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        if not rows:
            return []

        def _to_row(
            chunk: DocumentChunk, document: Document, version: DocumentVersion
        ) -> ChunkHydrationRow:
            return _to_hydration_row(chunk, document, version)

        headings = [
            (chunk, document, version)
            for chunk, document, version in rows
            if chunk.layout_type == ChunkLayoutType.heading
        ]
        picked: list[ChunkHydrationRow] = [_to_row(*rows[0])]  # first chunk (title/intro)
        remaining = max(0, limit - 2)  # reserve slots for first + last
        if headings and remaining > 0:
            step = max(1, len(headings) // remaining)
            for chunk, document, version in headings[::step][:remaining]:
                picked.append(_to_row(chunk, document, version))
        if len(rows) > 1:
            picked.append(_to_row(*rows[-1]))  # last chunk (conclusion/signature)

        seen: set[uuid.UUID] = set()
        deduped: list[ChunkHydrationRow] = []
        for row in picked:
            if row.chunk_id in seen:
                continue
            seen.add(row.chunk_id)
            deduped.append(row)
        return deduped[:limit]

    async def chunks_for_entity_versions(
        self,
        workspace_id: uuid.UUID,
        source_version_ids: list[uuid.UUID],
        *,
        entity_names: list[str],
        limit: int = 20,
    ) -> list[ChunkHydrationRow]:
        """Fallback graph hydration: chunks of entity versions mentioning entity names."""
        if not source_version_ids:
            return []
        name_filters = [
            DocumentChunk.content.ilike(f"%{name}%") for name in entity_names if name.strip()
        ]
        conditions = [
            Document.workspace_id == workspace_id,
            DocumentChunk.document_version_id.in_(source_version_ids),
        ]
        if name_filters:
            conditions.append(or_(*name_filters))
        stmt = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(*conditions)
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(max(1, limit))
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            _to_hydration_row(chunk, document, version)
            for chunk, document, version in rows
        ]

    async def list_chunks_for_document(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID | None = None,
    ) -> list[ChunkHydrationRow]:
        """List chunks for a document's current (or specified) version.

        Args:
            workspace_id: Tenant scope.
            document_id: Document id within the workspace.
            version_id: Optional version override; defaults to ``current_version_id``.

        Returns:
            Chunks ordered by ``chunk_index`` (empty if document/version missing).
        """
        doc_stmt = select(Document).where(
            Document.id == document_id,
            Document.workspace_id == workspace_id,
        )
        document = (await self._session.execute(doc_stmt)).scalar_one_or_none()
        if document is None:
            return []
        target_version = version_id or document.current_version_id
        if target_version is None:
            return []

        stmt = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.workspace_id == workspace_id,
                Document.id == document_id,
                DocumentChunk.document_version_id == target_version,
            )
            .order_by(DocumentChunk.chunk_index.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            _to_hydration_row(chunk, document, version)
            for chunk, document, version in rows
        ]

    async def search_heading_chunks(
        self,
        workspace_id: uuid.UUID,
        *,
        section_number: str | None = None,
        title_query: str | None = None,
        limit: int = 80,
    ) -> list[ChunkHydrationRow]:
        """Lexical heading search scoped to ``workspace_id`` (no vector / LLM).

        Matching order is applied by the caller. This query only bounds the
        candidate set using ``layout_type=heading`` plus ILIKE on
        ``content`` / ``section`` / ``heading_path``.
        """
        filters = [
            Document.workspace_id == workspace_id,
            DocumentChunk.layout_type == ChunkLayoutType.heading,
        ]
        text_filters = []
        title = (title_query or "").strip()
        if title:
            like = f"%{title}%"
            text_filters.append(
                or_(
                    DocumentChunk.content.ilike(like),
                    DocumentChunk.section.ilike(like),
                    DocumentChunk.heading_path.ilike(like),
                )
            )
        number = (section_number or "").strip()
        if number:
            number_filters = [
                DocumentChunk.content.ilike(f"{number}.%"),
                DocumentChunk.content.ilike(f"{number} %"),
                DocumentChunk.section.ilike(f"{number}.%"),
                DocumentChunk.section.ilike(f"{number} %"),
                DocumentChunk.content == number,
                DocumentChunk.section == number,
            ]
            text_filters.append(or_(*number_filters))
        if text_filters:
            filters.append(or_(*text_filters))

        stmt = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(*filters)
            .order_by(
                DocumentChunk.document_version_id.asc(),
                DocumentChunk.chunk_index.asc(),
            )
            .limit(max(1, limit))
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            _to_hydration_row(chunk, document, version)
            for chunk, document, version in rows
        ]

    async def list_child_chunks(
        self,
        workspace_id: uuid.UUID,
        parent_chunk_id: uuid.UUID,
        *,
        headings_only: bool = False,
        limit: int = 200,
    ) -> list[ChunkHydrationRow]:
        """Return direct children of ``parent_chunk_id`` in document order."""
        filters = [
            Document.workspace_id == workspace_id,
            DocumentChunk.parent_chunk_id == parent_chunk_id,
        ]
        if headings_only:
            filters.append(DocumentChunk.layout_type == ChunkLayoutType.heading)
        stmt = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(*filters)
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(max(1, limit))
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            _to_hydration_row(chunk, document, version)
            for chunk, document, version in rows
        ]

    async def list_chunks_by_heading_path_prefix(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
        heading_path: str,
        *,
        limit: int = 200,
    ) -> list[ChunkHydrationRow]:
        """Chunks whose ``heading_path`` is ``heading_path`` or a descendant."""
        path = (heading_path or "").strip()
        if not path:
            return []
        prefix = f"{path} > %"
        stmt = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.workspace_id == workspace_id,
                DocumentChunk.document_version_id == document_version_id,
                or_(
                    DocumentChunk.heading_path == path,
                    DocumentChunk.heading_path.like(prefix),
                ),
            )
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(max(1, limit))
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            _to_hydration_row(chunk, document, version)
            for chunk, document, version in rows
        ]

    async def list_version_heading_chunks(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
        *,
        limit: int = 400,
    ) -> list[ChunkHydrationRow]:
        """All heading chunks of a version, ordered by ``chunk_index``."""
        stmt = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(
                Document.workspace_id == workspace_id,
                DocumentChunk.document_version_id == document_version_id,
                DocumentChunk.layout_type == ChunkLayoutType.heading,
            )
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(max(1, limit))
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            _to_hydration_row(chunk, document, version)
            for chunk, document, version in rows
        ]

    async def list_chunks_in_index_range(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
        *,
        start_index: int,
        end_index: int | None,
        limit: int = 200,
    ) -> list[ChunkHydrationRow]:
        """Chunks in ``[start_index, end_index)`` for neighbor/section span fill."""
        filters = [
            Document.workspace_id == workspace_id,
            DocumentChunk.document_version_id == document_version_id,
            DocumentChunk.chunk_index >= start_index,
        ]
        if end_index is not None:
            filters.append(DocumentChunk.chunk_index < end_index)
        stmt = (
            select(DocumentChunk, Document, DocumentVersion)
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .where(*filters)
            .order_by(DocumentChunk.chunk_index.asc())
            .limit(max(1, limit))
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            _to_hydration_row(chunk, document, version)
            for chunk, document, version in rows
        ]

    async def list_top_chunks_by_topic(
        self,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        version_id: uuid.UUID,
        focus: str | None = None,
        limit: int = 8,
    ) -> list[ChunkHydrationRow]:
        """Rank version chunks by topic linkage (and optional focus name match).

        Chunks linked to more topics rank higher. When ``focus`` is set, chunks
        whose topic names ILIKE the focus are preferred. Falls back to
        ``chunk_index`` order when no topic links exist.
        """
        if limit <= 0:
            return []

        focus_term = (focus or "").strip()
        if focus_term:
            focus_score = func.coalesce(
                func.max(
                    case(
                        (Topic.name.ilike(f"%{focus_term}%"), 1),
                        else_=0,
                    )
                ),
                0,
            )
        else:
            focus_score = literal_column("0")

        stmt = (
            select(
                DocumentChunk,
                Document,
                DocumentVersion,
                func.count(TopicChunk.topic_id).label("link_count"),
                focus_score.label("focus_score"),
            )
            .join(
                DocumentVersion,
                DocumentVersion.id == DocumentChunk.document_version_id,
            )
            .join(Document, Document.id == DocumentVersion.document_id)
            .outerjoin(TopicChunk, TopicChunk.chunk_id == DocumentChunk.id)
            .outerjoin(Topic, Topic.id == TopicChunk.topic_id)
            .where(
                Document.workspace_id == workspace_id,
                Document.id == document_id,
                DocumentChunk.document_version_id == version_id,
            )
            .group_by(DocumentChunk.id, Document.id, DocumentVersion.id)
            .order_by(
                desc("focus_score"),
                desc("link_count"),
                DocumentChunk.chunk_index.asc(),
            )
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            _to_hydration_row(chunk, document, version)
            for chunk, document, version, _link_count, _focus_score in rows
        ]

    async def document_id_for_version(
        self,
        workspace_id: uuid.UUID,
        document_version_id: uuid.UUID,
    ) -> uuid.UUID | None:
        stmt = (
            select(Document.id)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                Document.workspace_id == workspace_id,
                DocumentVersion.id == document_version_id,
            )
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_documents_metadata(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
        uploaded_after: datetime | None = None,
        uploaded_before: datetime | None = None,
        title_contains: str | None = None,
        limit: int = 50,
    ) -> list[MetadataDocumentRow]:
        """List documents with current-version upload metadata (Postgres only)."""
        filters = [Document.workspace_id == workspace_id]
        if file_type is not None:
            filters.append(Document.file_type == file_type)
        if uploaded_after is not None:
            filters.append(Document.created_at >= uploaded_after)
        if uploaded_before is not None:
            filters.append(Document.created_at <= uploaded_before)
        if title_contains:
            filters.append(Document.title.ilike(f"%{title_contains.strip()}%"))

        stmt = (
            select(Document, DocumentVersion)
            .outerjoin(
                DocumentVersion,
                DocumentVersion.id == Document.current_version_id,
            )
            .where(*filters)
            .order_by(Document.created_at.desc())
            .limit(max(1, limit))
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            MetadataDocumentRow(
                document_id=doc.id,
                workspace_id=doc.workspace_id,
                title=doc.title,
                file_type=doc.file_type,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
                uploaded_by=version.uploaded_by if version else None,
                version_number=version.version_number if version else None,
                status=version.status.value if version else None,
            )
            for doc, version in rows
        ]

    async def count_documents(
        self,
        workspace_id: uuid.UUID,
        *,
        file_type: FileType | None = None,
    ) -> int:
        filters = [Document.workspace_id == workspace_id]
        if file_type is not None:
            filters.append(Document.file_type == file_type)
        stmt = select(func.count()).select_from(Document).where(*filters)
        return int((await self._session.execute(stmt)).scalar_one())

    async def count_by_file_type(
        self,
        workspace_id: uuid.UUID,
    ) -> dict[str, int]:
        stmt = (
            select(Document.file_type, func.count())
            .where(Document.workspace_id == workspace_id)
            .group_by(Document.file_type)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(ft.value if hasattr(ft, "value") else ft): int(cnt) for ft, cnt in rows}

    async def find_entities_by_name(
        self,
        workspace_id: uuid.UUID,
        query_text: str,
        *,
        limit: int = 20,
    ) -> list[Entity]:
        """Postgres entity fallback when Neo4j returns entity-only (no chunk link)."""
        q = (query_text or "").strip()
        if not q:
            return []
        stmt = (
            select(Entity)
            .where(
                Entity.workspace_id == workspace_id,
                Entity.name.ilike(f"%{q}%"),
            )
            .order_by(Entity.name.asc())
            .limit(max(1, limit))
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def documents_meta_by_ids(
        self,
        workspace_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, MetadataDocumentRow]:
        """Load document metadata for filter / title hydration (workspace-scoped)."""
        if not document_ids:
            return {}
        stmt = (
            select(Document, DocumentVersion)
            .outerjoin(
                DocumentVersion,
                DocumentVersion.id == Document.current_version_id,
            )
            .where(
                Document.workspace_id == workspace_id,
                Document.id.in_(document_ids),
            )
        )
        rows = (await self._session.execute(stmt)).all()
        out: dict[uuid.UUID, MetadataDocumentRow] = {}
        for doc, version in rows:
            out[doc.id] = MetadataDocumentRow(
                document_id=doc.id,
                workspace_id=doc.workspace_id,
                title=doc.title,
                file_type=doc.file_type,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
                uploaded_by=version.uploaded_by if version else None,
                version_number=version.version_number if version else None,
                status=version.status.value if version else None,
            )
        return out
