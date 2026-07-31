# =============================================================================
# File: metadata_search.py
# Module/Service: Search Service / Query Router — Metadata Retrieval
# Layer: Service
# Purpose: Postgres-only metadata retrieval for structured / listing queries (FR3/FR11).
# Responsibilities:
#   - List/count documents by file_type, time range, title; workspace stats
#   - Produce RetrievalCandidate-compatible snippets for reuse by Query Router
# Dependencies:
#   - app.repositories.retrieval, app.core.config
# Public Exports:
#   - MetadataSearch, MetadataSearchResult
# Database/Table: documents, document_versions
# Related Modules: HybridRetrievalService (sibling), Query Router (Part 2)
# Important Notes: 0 embedding / 0 ES / 0 Neo4j. Postgres only. 0 LLM.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enums import FileType
from app.repositories.retrieval import RetrievalRepository
from app.services.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)


@dataclass(slots=True)
class MetadataSearchResult:
    """Structured metadata answer plus optional candidate list for UI/search."""

    items: list[RetrievalCandidate]
    total_count: int
    counts_by_file_type: dict[str, int] = field(default_factory=dict)
    summary_text: str = ""


class MetadataSearch:
    """Metadata Retrieval — direct PostgreSQL queries (reused by Query Router)."""

    def __init__(
        self,
        *,
        settings: Settings,
        repo: RetrievalRepository,
    ) -> None:
        self._settings = settings
        self._repo = repo

    async def search(
        self,
        workspace_id: UUID,
        query_text: str,
        top_k: int = 20,
        *,
        file_type: FileType | None = None,
        uploaded_after: datetime | None = None,
        uploaded_before: datetime | None = None,
    ) -> MetadataSearchResult:
        """Query document metadata for ``workspace_id``.

        Interprets simple intent from ``query_text`` (count vs list) without LLM.

        Args:
            workspace_id: Tenant scope.
            query_text: Natural-language or keyword query (title contains).
            top_k: Max document rows when listing.
            file_type: Optional file-type filter.
            uploaded_after / uploaded_before: Optional created_at window.

        Returns:
            ``MetadataSearchResult`` with candidates and workspace statistics.
        """
        q = (query_text or "").strip()
        lower = q.lower()
        wants_count = any(
            token in lower
            for token in ("how many", "count", "số lượng", "bao nhiêu", "total")
        )

        counts = await self._repo.count_by_file_type(workspace_id)
        total = await self._repo.count_documents(workspace_id, file_type=file_type)

        title_contains = None if wants_count else (q or None)
        # Strip filter-ish words from title search heuristically.
        if title_contains and wants_count:
            title_contains = None

        docs = await self._repo.list_documents_metadata(
            workspace_id,
            file_type=file_type,
            uploaded_after=uploaded_after,
            uploaded_before=uploaded_before,
            title_contains=title_contains,
            limit=top_k,
        )

        max_chars = self._settings.retrieval_snippet_max_chars
        items: list[RetrievalCandidate] = []
        for doc in docs:
            snippet = (
                f"{doc.title} | type={doc.file_type.value} | "
                f"version={doc.version_number} | status={doc.status} | "
                f"created_at={doc.created_at.isoformat()}"
            )[:max_chars]
            items.append(
                RetrievalCandidate(
                    workspace_id=workspace_id,
                    document_id=doc.document_id,
                    text_snippet=snippet,
                    raw_score=1.0,
                    retrieval_method="metadata",
                    source_methods=["metadata"],
                )
            )

        if wants_count:
            by_type = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
            summary = f"Workspace has {total} document(s)" + (
                f" (filter file_type={file_type.value})" if file_type else ""
            )
            if by_type != "none":
                summary = f"{summary}. By type: {by_type}."
        else:
            summary = f"Found {len(items)} document(s) matching metadata filters (total={total})."

        logger.info(
            "metadata_search_completed",
            workspace_id=str(workspace_id),
            total_count=total,
            results=len(items),
            wants_count=wants_count,
        )
        return MetadataSearchResult(
            items=items,
            total_count=total,
            counts_by_file_type=counts,
            summary_text=summary,
        )
