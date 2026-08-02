# =============================================================================
# File: metadata_repository_adapter.py
# Module/Service: Query Router — Metadata Branch (FR11)
# Layer: Adapter
# Purpose: Adapt RetrievalRepository + member repo to MetadataRepository Protocol.
# Responsibilities:
#   - Bridge existing retrieval metadata helpers to whitelist method names
# Dependencies:
#   - RetrievalRepository, WorkspaceMemberRepository
# Public Exports:
#   - RetrievalMetadataRepositoryAdapter
# Database/Table: via RetrievalRepository
# Related Modules: metadata_branch, MetadataHandler
# Important Notes: Prefer PostgresMetadataRepository in production DI.
# =============================================================================

from __future__ import annotations

from uuid import UUID

from app.models.enums import FileType
from app.repositories.retrieval import RetrievalRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.query_router.interfaces.metadata_repository import MetadataDocumentInfo


class RetrievalMetadataRepositoryAdapter:
    """Adapt ``RetrievalRepository`` to ``MetadataRepository`` method names."""

    def __init__(
        self,
        retrieval_repo: RetrievalRepository,
        member_repo: WorkspaceMemberRepository | None = None,
        *,
        list_limit: int = 50,
    ) -> None:
        self._docs = retrieval_repo
        self._members = member_repo
        self._list_limit = max(1, list_limit)

    async def count_documents(
        self,
        workspace_id: UUID,
        *,
        file_type: FileType | None = None,
    ) -> int:
        return int(await self._docs.count_documents(workspace_id, file_type=file_type))

    async def count_files(
        self,
        workspace_id: UUID,
        *,
        file_type: FileType | None = None,
    ) -> int:
        return await self.count_documents(workspace_id, file_type=file_type)

    async def count_pdf(self, workspace_id: UUID) -> int:
        return await self.count_documents(workspace_id, file_type=FileType.pdf)

    async def list_documents(
        self,
        workspace_id: UUID,
        *,
        file_type: FileType | None = None,
        limit: int = 50,
    ) -> list[MetadataDocumentInfo]:
        rows = await self._docs.list_documents_metadata(
            workspace_id, file_type=file_type, limit=limit
        )
        return [
            MetadataDocumentInfo(
                document_id=r.document_id,
                title=r.title,
                file_type=r.file_type.value,
                created_at=r.created_at,
                uploaded_by=r.uploaded_by,
            )
            for r in rows
        ]

    async def latest_documents(
        self,
        workspace_id: UUID,
        *,
        limit: int = 10,
    ) -> list[MetadataDocumentInfo]:
        return await self.list_documents(workspace_id, limit=limit)

    async def oldest_documents(
        self,
        workspace_id: UUID,
        *,
        limit: int = 10,
    ) -> list[MetadataDocumentInfo]:
        # RetrievalRepository lists newest-first; reverse for oldest preview.
        rows = await self.list_documents(workspace_id, limit=max(limit * 3, limit))
        rows_sorted = sorted(
            rows,
            key=lambda r: r.created_at or r.document_id.int,
        )
        return rows_sorted[:limit]

    async def count_chunks(self, workspace_id: UUID) -> int:
        counter = getattr(self._docs, "count_chunks", None)
        if callable(counter):
            return int(await counter(workspace_id))
        return 0

    async def count_pages(self, workspace_id: UUID) -> int:
        counter = getattr(self._docs, "count_pages", None)
        if callable(counter):
            return int(await counter(workspace_id))
        return 0

    async def count_members(self, workspace_id: UUID) -> int:
        if self._members is None:
            return 0
        return int(await self._members.count_active_members(workspace_id))

    async def stats_by_file_type(self, workspace_id: UUID) -> dict[str, int]:
        return dict(await self._docs.count_by_file_type(workspace_id))

    async def document_owner(
        self,
        workspace_id: UUID,
        *,
        document_id: UUID | None = None,
    ) -> MetadataDocumentInfo | None:
        rows = await self.list_documents(workspace_id, limit=self._list_limit)
        if document_id is not None:
            for row in rows:
                if row.document_id == document_id:
                    return row
            return None
        return rows[0] if rows else None
