# =============================================================================
# File: metadata_branch.py
# Module/Service: Query Router Execution / Metadata Branch
# Layer: Service
# Purpose: Compat facade over MetadataHandler (whitelist metadata, 0 LLM).
# Responsibilities:
#   - Delegate to MetadataHandler; preserve MetadataBranchResult for orchestrator
#   - Re-export map_metadata_intent for legacy unit tests
# Dependencies:
#   - MetadataHandler, RetrievalMetadataRepositoryAdapter
# Public Exports:
#   - MetadataBranch, MetadataIntent, map_metadata_intent, MetadataBranchResult
# Database/Table: via MetadataRepository
# Related Modules: orchestrator, handlers.metadata_handler
# Important Notes: Never generate SQL; unknown whitelist → complex fallback.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.models.enums import FileType, RouteType
from app.repositories.retrieval import RetrievalRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.query_router.handlers.metadata_handler import MetadataHandler
from app.services.query_router.interfaces.metadata_repository import MetadataRepository
from app.services.query_router.metadata_registry import (
    MetadataRegistry,
    detect_file_type,
)
from app.services.query_router.metadata_repository_adapter import (
    RetrievalMetadataRepositoryAdapter,
)
from app.services.query_router.schemas import CitationRef, RouteDecision


class MetadataIntent(StrEnum):
    """Whitelist of supported metadata query intents (no dynamic SQL)."""

    COUNT_DOCUMENTS = "count_documents"
    COUNT_BY_FILE_TYPE = "count_by_file_type"
    LIST_DOCUMENTS = "list_documents"
    LIST_BY_FILE_TYPE = "list_by_file_type"
    COUNT_MEMBERS = "count_members"
    STATS_FILE_TYPE = "stats_file_type"
    RECENT_UPLOADS = "recent_uploads"
    LATEST_DOCUMENTS = "latest_documents"
    OLDEST_DOCUMENTS = "oldest_documents"
    DOCUMENT_OWNER = "document_owner"


@dataclass(slots=True)
class MetadataBranchResult:
    """Result of Metadata Branch execution (may signal complex fallback)."""

    route_type: RouteType
    answer: str | None
    citation_refs: list[CitationRef]
    metadata: dict[str, Any]
    verify: bool
    status: str | None = None
    intent: MetadataIntent | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None


def map_metadata_intent(query_text: str) -> tuple[MetadataIntent | None, FileType | None]:
    """Map query text to a whitelist intent (compat for legacy tests)."""
    match = MetadataRegistry().match(query_text)
    if match is None:
        return None, None
    name = match.rule.intent
    ft = match.file_type
    if name == "count_pdf":
        return MetadataIntent.COUNT_BY_FILE_TYPE, FileType.pdf
    if name == "count_documents":
        if ft is not None:
            return MetadataIntent.COUNT_BY_FILE_TYPE, ft
        return MetadataIntent.COUNT_DOCUMENTS, None
    if name == "list_documents":
        if ft is not None:
            return MetadataIntent.LIST_BY_FILE_TYPE, ft
        return MetadataIntent.LIST_DOCUMENTS, None
    if name == "latest_documents":
        return MetadataIntent.RECENT_UPLOADS, None
    if name == "oldest_documents":
        return MetadataIntent.OLDEST_DOCUMENTS, None
    if name == "count_members":
        return MetadataIntent.COUNT_MEMBERS, None
    if name == "stats_file_type":
        return MetadataIntent.STATS_FILE_TYPE, None
    if name == "document_owner":
        return MetadataIntent.DOCUMENT_OWNER, None
    return None, None


class MetadataBranch:
    """Whitelist-only metadata query executor (delegates to ``MetadataHandler``)."""

    def __init__(
        self,
        *,
        retrieval_repo: RetrievalRepository | None = None,
        member_repo: WorkspaceMemberRepository | None = None,
        handler: MetadataHandler | None = None,
        metadata_repo: MetadataRepository | None = None,
        list_limit: int = 50,
        recent_limit: int = 10,
    ) -> None:
        if handler is not None:
            self._handler = handler
        else:
            repo = metadata_repo
            if repo is None:
                if retrieval_repo is None:
                    raise TypeError("retrieval_repo, metadata_repo, or handler required")
                repo = RetrievalMetadataRepositoryAdapter(
                    retrieval_repo,
                    member_repo,
                    list_limit=list_limit,
                )
            self._handler = MetadataHandler(
                repository=repo,
                list_limit=list_limit,
                recent_limit=recent_limit,
            )

    async def execute(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
        decision: RouteDecision,
    ) -> MetadataBranchResult:
        """Execute a metadata-classified query via whitelist mapping."""
        del user_id, decision
        result = await self._handler.handle(
            workspace_id=workspace_id,
            query_text=query_text,
        )
        intent, _ = map_metadata_intent(query_text)
        return MetadataBranchResult(
            route_type=result.route_type,
            answer=result.answer,
            citation_refs=list(result.citation_refs),
            metadata=dict(result.metadata),
            verify=result.verify,
            status=result.status,
            intent=intent,
            confidence=result.confidence,
            extras={},
        )


__all__ = [
    "MetadataBranch",
    "MetadataBranchResult",
    "MetadataIntent",
    "detect_file_type",
    "map_metadata_intent",
]
