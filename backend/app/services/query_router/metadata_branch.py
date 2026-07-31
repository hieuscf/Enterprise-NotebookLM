# =============================================================================
# File: metadata_branch.py
# Module/Service: Query Router Execution / Metadata Branch
# Layer: Service
# Purpose: Execute whitelist-mapped metadata queries (0 LLM, no Text-to-SQL).
# Responsibilities:
#   - Map metadata query_text → fixed MetadataIntent via regex/keywords
#   - Call repository helpers only; fallback to complex when unknown
# Dependencies:
#   - RetrievalRepository, WorkspaceMemberRepository
# Public Exports:
#   - MetadataBranch, MetadataIntent, map_metadata_intent
# Database/Table: documents, workspace_members (via repos)
# Related Modules: app.services.query_router.orchestrator
# Important Notes: Never generate SQL; unknown whitelist → complex fallback.
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.models.enums import FileType, RouteType
from app.repositories.retrieval import RetrievalRepository
from app.repositories.workspace_members import WorkspaceMemberRepository
from app.services.query_router.cache import normalize_query
from app.services.query_router.schemas import CitationRef, RouteDecision

logger = get_logger(__name__)


class MetadataIntent(StrEnum):
    """Whitelist of supported metadata query intents (no dynamic SQL)."""

    COUNT_DOCUMENTS = "count_documents"
    COUNT_BY_FILE_TYPE = "count_by_file_type"
    LIST_DOCUMENTS = "list_documents"
    LIST_BY_FILE_TYPE = "list_by_file_type"
    COUNT_MEMBERS = "count_members"
    STATS_FILE_TYPE = "stats_file_type"
    RECENT_UPLOADS = "recent_uploads"


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


_FILE_TYPE_ALIASES: tuple[tuple[re.Pattern[str], FileType], ...] = (
    (re.compile(r"\bpdfs?\b", re.IGNORECASE), FileType.pdf),
    (re.compile(r"\bdocx?\b", re.IGNORECASE), FileType.docx),
    (re.compile(r"\bxlsx?\b", re.IGNORECASE), FileType.xlsx),
    (re.compile(r"\bpptx?\b", re.IGNORECASE), FileType.pptx),
    (re.compile(r"\btxts?\b|\btext\s+files?\b", re.IGNORECASE), FileType.txt),
)

# Unsupported intents that metadata classifier may still match → complex fallback.
_UNSUPPORTED = re.compile(
    r"(?:\btags?\b|thống\s*kê\s*tag|tag\s*stats)",
    re.IGNORECASE | re.UNICODE,
)

_COUNT_MEMBERS = re.compile(
    r"(?:"
    r"(?:đếm|có\s*bao\s*nhiêu|số\s*lượng|tổng\s*số).{0,40}(?:thành\s*viên|member)"
    r"|(?:how\s*many|number\s*of|count).{0,40}members?"
    r"|count\s*members?"
    r")",
    re.IGNORECASE | re.UNICODE,
)

_STATS_FILE_TYPE = re.compile(
    r"(?:"
    r"thống\s*kê.{0,40}(?:loại|file\s*type|kiểu\s*file)"
    r"|stats?(?:\s*by)?\s*file\s*type"
    r"|file\s*type\s*stats?"
    r"|count\s*by\s*(?:file\s*)?type"
    r")",
    re.IGNORECASE | re.UNICODE,
)

_RECENT_UPLOADS = re.compile(
    r"(?:"
    r"(?:upload|tải\s*lên).{0,20}(?:gần\s*đây|mới\s*nhất|recent)"
    r"|recent\s*uploads?"
    r"|uploaded\s*recently"
    r"|tài\s*liệu\s*mới\s*nhất"
    r")",
    re.IGNORECASE | re.UNICODE,
)

_COUNT_DOCS = re.compile(
    r"(?:"
    r"(?:có\s*)?bao\s*nhiêu\s*(?:tài\s*liệu|document|file)"
    r"|đếm\s*(?:số\s*)?(?:tài\s*liệu|document|file)"
    r"|số\s*lượng\s*(?:tài\s*liệu|document|file)"
    r"|tổng\s*số\s*(?:tài\s*liệu|document|file)"
    r"|how\s*many\s*(?:documents?|files?)"
    r"|number\s*of\s*(?:documents?|files?)"
    r"|count\s*(?:the\s*)?(?:documents?|files?)"
    r")",
    re.IGNORECASE | re.UNICODE,
)

_LIST_DOCS = re.compile(
    r"(?:"
    r"liệt\s*kê\s*(?:tài\s*liệu|document|file)?"
    r"|danh\s*sách\s*(?:tài\s*liệu|document|file)?"
    r"|list\s*(?:all\s*)?(?:documents?|files?)?"
    r"|show\s*all\s*(?:documents?|files?)?"
    r")",
    re.IGNORECASE | re.UNICODE,
)


def detect_file_type(query: str) -> FileType | None:
    """Extract a single file type mention from ``query``, if any."""
    for pattern, ft in _FILE_TYPE_ALIASES:
        if pattern.search(query):
            return ft
    return None


def map_metadata_intent(query_text: str) -> tuple[MetadataIntent | None, FileType | None]:
    """Map normalized query text to a whitelist intent (or ``None``).

    Args:
        query_text: Raw or normalized user question classified as metadata.

    Returns:
        ``(intent, file_type)`` where ``file_type`` is set for type-scoped intents.
        ``(None, None)`` means fallback to complex — do not guess.
    """
    q = normalize_query(query_text)
    if not q:
        return None, None
    if _UNSUPPORTED.search(q):
        return None, None

    file_type = detect_file_type(q)

    if _COUNT_MEMBERS.search(q):
        return MetadataIntent.COUNT_MEMBERS, None
    if _STATS_FILE_TYPE.search(q):
        return MetadataIntent.STATS_FILE_TYPE, None
    if _RECENT_UPLOADS.search(q):
        return MetadataIntent.RECENT_UPLOADS, None

    if _COUNT_DOCS.search(q) or (
        re.search(r"\bcount\b", q, re.IGNORECASE) and file_type is not None
    ):
        if file_type is not None:
            return MetadataIntent.COUNT_BY_FILE_TYPE, file_type
        return MetadataIntent.COUNT_DOCUMENTS, None

    if _LIST_DOCS.search(q):
        if file_type is not None:
            return MetadataIntent.LIST_BY_FILE_TYPE, file_type
        return MetadataIntent.LIST_DOCUMENTS, None

    # Bare "danh sách PDF" / "PDF count" style without list/count verb already covered;
    # leftover file-type-only phrases → list by type when list-like keyword present.
    if file_type is not None and re.search(
        r"(?:danh\s*sách|list|show|liệt\s*kê)", q, re.IGNORECASE
    ):
        return MetadataIntent.LIST_BY_FILE_TYPE, file_type

    return None, None


class MetadataBranch:
    """Whitelist-only metadata query executor (0 LLM)."""

    def __init__(
        self,
        *,
        retrieval_repo: RetrievalRepository,
        member_repo: WorkspaceMemberRepository,
        list_limit: int = 50,
        recent_limit: int = 10,
    ) -> None:
        self._docs = retrieval_repo
        self._members = member_repo
        self._list_limit = max(1, list_limit)
        self._recent_limit = max(1, recent_limit)

    async def execute(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        query_text: str,
        decision: RouteDecision,
    ) -> MetadataBranchResult:
        """Execute a metadata-classified query via whitelist mapping.

        Args:
            workspace_id: Tenant scope (RBAC enforced by caller).
            user_id: Authenticated user (observability only).
            query_text: Original user question.
            decision: Router ``RouteDecision`` with ``route_type=metadata``.

        Returns:
            Branch result; ``route_type=complex`` when intent is not whitelisted.
        """
        del user_id, decision  # reserved for future audit; workspace scoped via repos
        intent, file_type = map_metadata_intent(query_text)
        if intent is None:
            logger.info(
                "metadata_branch_fallback_complex",
                workspace_id=str(workspace_id),
                reason="unknown_whitelist",
            )
            return MetadataBranchResult(
                route_type=RouteType.complex,
                answer=None,
                citation_refs=[],
                metadata={},
                verify=False,
                status="pending_llm_pipeline",
                extras={"fallback_reason": "unknown_metadata_intent"},
            )

        if intent == MetadataIntent.COUNT_DOCUMENTS:
            count = await self._docs.count_documents(workspace_id)
            return _ok(
                intent,
                answer=f"Có {count} tài liệu trong workspace.",
                metadata={"count": count},
            )

        if intent == MetadataIntent.COUNT_BY_FILE_TYPE and file_type is not None:
            count = await self._docs.count_documents(workspace_id, file_type=file_type)
            label = file_type.value.upper()
            return _ok(
                intent,
                answer=f"Có {count} tài liệu {label} trong workspace.",
                metadata={"count": count, "file_type": file_type.value},
            )

        if intent == MetadataIntent.LIST_DOCUMENTS:
            rows = await self._docs.list_documents_metadata(
                workspace_id, limit=self._list_limit
            )
            titles = [r.title for r in rows]
            return _ok(
                intent,
                answer=_list_answer(titles, total_hint=len(rows)),
                metadata={
                    "documents": [
                        {
                            "document_id": str(r.document_id),
                            "title": r.title,
                            "file_type": r.file_type.value,
                        }
                        for r in rows
                    ],
                    "count": len(rows),
                },
            )

        if intent == MetadataIntent.LIST_BY_FILE_TYPE and file_type is not None:
            rows = await self._docs.list_documents_metadata(
                workspace_id, file_type=file_type, limit=self._list_limit
            )
            titles = [r.title for r in rows]
            return _ok(
                intent,
                answer=_list_answer(
                    titles,
                    total_hint=len(rows),
                    prefix=f"Tài liệu {file_type.value.upper()}",
                ),
                metadata={
                    "documents": [
                        {
                            "document_id": str(r.document_id),
                            "title": r.title,
                            "file_type": r.file_type.value,
                        }
                        for r in rows
                    ],
                    "count": len(rows),
                    "file_type": file_type.value,
                },
            )

        if intent == MetadataIntent.COUNT_MEMBERS:
            count = await self._members.count_active_members(workspace_id)
            return _ok(
                intent,
                answer=f"Workspace có {count} thành viên.",
                metadata={"count": count},
            )

        if intent == MetadataIntent.STATS_FILE_TYPE:
            stats = await self._docs.count_by_file_type(workspace_id)
            parts = [f"{k}: {v}" for k, v in sorted(stats.items())]
            summary = ", ".join(parts) if parts else "không có tài liệu"
            return _ok(
                intent,
                answer=f"Thống kê theo loại file — {summary}.",
                metadata={"by_file_type": stats, "count": sum(stats.values())},
            )

        if intent == MetadataIntent.RECENT_UPLOADS:
            rows = await self._docs.list_documents_metadata(
                workspace_id, limit=self._recent_limit
            )
            titles = [r.title for r in rows]
            return _ok(
                intent,
                answer=_list_answer(titles, total_hint=len(rows), prefix="Upload gần đây"),
                metadata={
                    "documents": [
                        {
                            "document_id": str(r.document_id),
                            "title": r.title,
                            "file_type": r.file_type.value,
                            "created_at": r.created_at.isoformat(),
                        }
                        for r in rows
                    ],
                    "count": len(rows),
                },
            )

        # Defensive: enum extended without handler.
        return MetadataBranchResult(
            route_type=RouteType.complex,
            answer=None,
            citation_refs=[],
            metadata={},
            verify=False,
            status="pending_llm_pipeline",
            extras={"fallback_reason": f"unhandled_intent={intent}"},
        )


def _ok(
    intent: MetadataIntent,
    *,
    answer: str,
    metadata: dict[str, Any],
) -> MetadataBranchResult:
    return MetadataBranchResult(
        route_type=RouteType.metadata,
        answer=answer,
        citation_refs=[],
        metadata=metadata,
        verify=True,
        intent=intent,
    )


def _list_answer(
    titles: list[str],
    *,
    total_hint: int,
    prefix: str = "Danh sách tài liệu",
) -> str:
    if not titles:
        return f"{prefix}: không có kết quả."
    preview = ", ".join(titles[:5])
    more = "" if total_hint <= 5 else f" (và {total_hint - 5} nữa)"
    return f"{prefix} ({total_hint}): {preview}{more}."
