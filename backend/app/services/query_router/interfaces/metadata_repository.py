# =============================================================================
# File: metadata_repository.py
# Module/Service: Query Router — Metadata Branch (FR11)
# Layer: Adapter (Protocol)
# Purpose: MetadataRepository Protocol — whitelist DB ops only (0 LLM / 0 SQL-in-handler).
# Responsibilities:
#   - Declare fixed repository methods mapped by MetadataRule
# Dependencies:
#   - N/A (Protocol only)
# Public Exports:
#   - MetadataDocumentInfo, MetadataRepository
# Database/Table: documents, document_chunks, workspace_members (via impl)
# Related Modules: handlers.metadata_handler, repositories.metadata_query
# Important Notes: No text-to-SQL; handlers call named methods only.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.models.enums import FileType


@dataclass(frozen=True, slots=True)
class MetadataDocumentInfo:
    """Minimal document row for list / latest / oldest / owner templates."""

    document_id: UUID
    title: str
    file_type: str
    created_at: datetime | None = None
    uploaded_by: UUID | None = None


@runtime_checkable
class MetadataRepository(Protocol):
    """Whitelist metadata DB operations (workspace-scoped)."""

    async def count_documents(
        self,
        workspace_id: UUID,
        *,
        file_type: FileType | None = None,
    ) -> int: ...

    async def count_files(
        self,
        workspace_id: UUID,
        *,
        file_type: FileType | None = None,
    ) -> int: ...

    async def count_pdf(self, workspace_id: UUID) -> int: ...

    async def list_documents(
        self,
        workspace_id: UUID,
        *,
        file_type: FileType | None = None,
        limit: int = 50,
    ) -> list[MetadataDocumentInfo]: ...

    async def latest_documents(
        self,
        workspace_id: UUID,
        *,
        limit: int = 10,
    ) -> list[MetadataDocumentInfo]: ...

    async def oldest_documents(
        self,
        workspace_id: UUID,
        *,
        limit: int = 10,
    ) -> list[MetadataDocumentInfo]: ...

    async def count_chunks(self, workspace_id: UUID) -> int: ...

    async def count_pages(self, workspace_id: UUID) -> int: ...

    async def count_members(self, workspace_id: UUID) -> int: ...

    async def stats_by_file_type(self, workspace_id: UUID) -> dict[str, int]: ...

    async def document_owner(
        self,
        workspace_id: UUID,
        *,
        document_id: UUID | None = None,
    ) -> MetadataDocumentInfo | None: ...
