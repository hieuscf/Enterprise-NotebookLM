# =============================================================================
# File: metadata_handler.py
# Module/Service: Query Router — Metadata Handler (FR11)
# Layer: Service
# Purpose: Execute whitelist metadata intents via registry + templates (0 LLM).
# Responsibilities:
#   - Match MetadataRule → call MetadataRepository method → render template
#   - Unsupported whitelist miss → route_type=complex (no guessing)
# Dependencies:
#   - MetadataRegistry, MetadataRepository, templates, QueryRouterResult
# Public Exports:
#   - MetadataHandler
# Database/Table: via MetadataRepository only
# Related Modules: orchestrator, metadata_branch (compat facade)
# Important Notes: No Retrieval / Embedding / LLM / dynamic SQL.
# =============================================================================

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.core.logging import get_logger
from app.models.enums import FileType, RouteType
from app.services.query_router.interfaces.metadata_repository import (
    MetadataDocumentInfo,
    MetadataRepository,
)
from app.services.query_router.metadata_registry import MetadataMatch, MetadataRegistry
from app.services.query_router.response_models import QueryRouterResult
from app.services.query_router.templates import list_preview, render_template

logger = get_logger(__name__)

COMPLEX_STATUS = "pending_llm_pipeline"


class MetadataHandler:
    """Whitelist-only metadata executor returning ``QueryRouterResult``."""

    def __init__(
        self,
        *,
        repository: MetadataRepository,
        registry: MetadataRegistry | None = None,
        list_limit: int = 50,
        recent_limit: int = 10,
    ) -> None:
        self._repo = repository
        self._registry = registry or MetadataRegistry()
        self._list_limit = max(1, list_limit)
        self._recent_limit = max(1, recent_limit)

    async def handle(
        self,
        *,
        workspace_id: UUID,
        query_text: str,
    ) -> QueryRouterResult:
        """Execute a metadata-classified query.

        Args:
            workspace_id: Tenant scope.
            query_text: Original user question.

        Returns:
            ``QueryRouterResult`` with ``metadata`` or ``complex`` on miss.
        """
        match = self._registry.match(query_text)
        if match is None:
            logger.info(
                "metadata_handler_unsupported",
                workspace_id=str(workspace_id),
                reason="unknown_whitelist",
            )
            return QueryRouterResult(
                route_type=RouteType.complex,
                answer=None,
                citation_refs=[],
                confidence=None,
                verify=False,
                status=COMPLEX_STATUS,
                metadata={"fallback_reason": "unknown_metadata_intent"},
            )

        try:
            answer, meta = await self._dispatch(workspace_id, match)
        except Exception:
            logger.exception(
                "metadata_handler_failed",
                workspace_id=str(workspace_id),
                intent=match.rule.intent,
            )
            return QueryRouterResult(
                route_type=RouteType.complex,
                answer=None,
                citation_refs=[],
                confidence=None,
                verify=False,
                status=COMPLEX_STATUS,
                metadata={"fallback_reason": f"handler_error:{match.rule.intent}"},
            )

        logger.info(
            "metadata_handler_ok",
            workspace_id=str(workspace_id),
            intent=match.rule.intent,
            method=match.rule.repository_method,
        )
        return QueryRouterResult(
            route_type=RouteType.metadata,
            answer=answer,
            citation_refs=[],
            confidence=1.0,
            verify=True,
            status=None,
            metadata={"intent": match.rule.intent, **meta},
        )

    async def _dispatch(
        self,
        workspace_id: UUID,
        match: MetadataMatch,
    ) -> tuple[str, dict[str, Any]]:
        rule = match.rule
        method = rule.repository_method
        en = match.prefer_english
        tmpl = rule.template_en if en and rule.template_en else rule.template

        if method == "count_documents":
            ft = match.file_type
            count = await self._repo.count_documents(workspace_id, file_type=ft)
            if ft is not None:
                key = "count_by_type_en" if en else "count_by_type_vi"
                return (
                    render_template(key, count=count, file_type=ft.value.upper()),
                    {"count": count, "file_type": ft.value},
                )
            return render_template(tmpl, count=count), {"count": count}

        if method == "count_pdf":
            count = await self._repo.count_pdf(workspace_id)
            return render_template(tmpl, count=count), {"count": count, "file_type": "pdf"}

        if method == "count_files":
            count = await self._repo.count_files(workspace_id)
            return render_template(tmpl, count=count), {"count": count}

        if method == "list_documents":
            ft = match.file_type
            rows = await self._repo.list_documents(
                workspace_id, file_type=ft, limit=self._list_limit
            )
            return self._list_result(rows, tmpl=tmpl, en=en, file_type=ft)

        if method == "latest_documents":
            rows = await self._repo.latest_documents(
                workspace_id, limit=self._recent_limit
            )
            return self._list_result(rows, tmpl=tmpl, en=en)

        if method == "oldest_documents":
            rows = await self._repo.oldest_documents(
                workspace_id, limit=self._recent_limit
            )
            return self._list_result(rows, tmpl=tmpl, en=en)

        if method == "count_members":
            count = await self._repo.count_members(workspace_id)
            return render_template(tmpl, count=count), {"count": count}

        if method == "stats_by_file_type":
            stats = await self._repo.stats_by_file_type(workspace_id)
            parts = [f"{k}: {v}" for k, v in sorted(stats.items())]
            summary = ", ".join(parts) if parts else ("no documents" if en else "không có tài liệu")
            return (
                render_template(tmpl, summary=summary),
                {"by_file_type": stats, "count": sum(stats.values())},
            )

        if method == "count_chunks":
            count = await self._repo.count_chunks(workspace_id)
            return render_template(tmpl, count=count), {"count": count}

        if method == "count_pages":
            count = await self._repo.count_pages(workspace_id)
            return render_template(tmpl, count=count), {"count": count}

        if method == "document_owner":
            info = await self._repo.document_owner(workspace_id)
            if info is None or info.uploaded_by is None:
                key = "document_owner_unknown_en" if en else "document_owner_unknown_vi"
                return render_template(key), {"owner_id": None}
            return (
                render_template(
                    tmpl,
                    owner_id=str(info.uploaded_by),
                    title=info.title,
                ),
                {
                    "owner_id": str(info.uploaded_by),
                    "document_id": str(info.document_id),
                    "title": info.title,
                },
            )

        raise ValueError(f"Unhandled repository_method={method}")

    def _list_result(
        self,
        rows: list[MetadataDocumentInfo],
        *,
        tmpl: str,
        en: bool,
        file_type: FileType | None = None,
    ) -> tuple[str, dict[str, Any]]:
        titles = [r.title for r in rows]
        preview, more, count = list_preview(titles)
        meta: dict[str, Any] = {
            "documents": [
                {
                    "document_id": str(r.document_id),
                    "title": r.title,
                    "file_type": r.file_type,
                }
                for r in rows
            ],
            "count": count,
        }
        if file_type is not None:
            meta["file_type"] = file_type.value
            key = "list_by_type_en" if en else "list_by_type_vi"
            if count == 0:
                empty = "empty_list_en" if en else "empty_list_vi"
                prefix = f"{file_type.value.upper()} documents" if en else f"Tài liệu {file_type.value.upper()}"
                return render_template(empty, prefix=prefix), meta
            return (
                render_template(
                    key,
                    count=count,
                    preview=preview,
                    more=more,
                    file_type=file_type.value.upper(),
                ),
                meta,
            )
        if count == 0:
            empty = "empty_list_en" if en else "empty_list_vi"
            prefix = "Documents" if en else "Danh sách tài liệu"
            return render_template(empty, prefix=prefix), meta
        return render_template(tmpl, count=count, preview=preview, more=more), meta
