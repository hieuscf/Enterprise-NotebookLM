# =============================================================================
# File: report_service.py
# Module/Service: Report Service (FR9)
# Layer: Service
# Purpose: Async report request + generation (aggregate → render → store).
# Responsibilities:
#   - request_report: validate sources, create pending row, enqueue Celery
#   - process_report: aggregate blocks, render by export_format, upload MinIO
#   - list / get / delete / export for HTTP API
# Dependencies:
#   - ReportRepository, ReportAggregationService, renderers, MinioStorageAdapter
# Public Exports:
#   - ReportService, ReportServiceError, ReportExportPayload
# Database/Table: reports, report_items
# Related Modules: app.workers.reports, OpenAPI Reports, report_aggregation
# Important Notes:
#   - HTTP path must not render files; generation runs in process_report only.
#   - Schema v1 has no reports.error — failures set status=failed and log detail.
#   - DB column ``format`` maps to OpenAPI ``export_format``;
#     ``file_path`` (MinIO key) maps to response ``file_url`` (export route).
# =============================================================================

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.minio_storage import MinioStorageAdapter
from app.core.logging import get_logger
from app.models.artifacts import Report
from app.models.enums import ReportFormat, ReportSourceType, ReportStatus
from app.repositories.reports import ReportItemSpec, ReportRepository, ReportWithItems
from app.services.report_aggregation import (
    AggregatedReportBlock,
    ReportAggregationError,
    ReportAggregationService,
    ReportItemInput as AggregationItem,
)
from app.services.renderers.docx_renderer import DocxRenderResult, render_docx
from app.services.renderers.markdown_renderer import MarkdownRenderResult, render_markdown
from app.services.renderers.pdf_renderer import PdfRenderResult, render_pdf

logger = get_logger(__name__)

EnqueueFn = Callable[[uuid.UUID], None]

CONTENT_TYPES: dict[ReportFormat, str] = {
    ReportFormat.pdf: "application/pdf",
    ReportFormat.docx: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ReportFormat.markdown: "text/markdown; charset=utf-8",
}

MarkdownRenderFn = Callable[..., MarkdownRenderResult]
DocxRenderFn = Callable[..., DocxRenderResult]
PdfRenderFn = Callable[..., PdfRenderResult]


@dataclass(frozen=True, slots=True)
class ReportExportPayload:
    data: bytes
    content_type: str
    filename: str


class ReportServiceError(Exception):
    """Domain error mapped to HTTP by the presentation layer."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ReportService:
    """Application service for FR9 Report Generation & Export."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        reports: ReportRepository,
        aggregation: ReportAggregationService,
        storage: MinioStorageAdapter,
        enqueue: bool = True,
        enqueue_fn: EnqueueFn | None = None,
        markdown_render_fn: MarkdownRenderFn | None = None,
        docx_render_fn: DocxRenderFn | None = None,
        pdf_render_fn: PdfRenderFn | None = None,
        staging_dir: Path | None = None,
    ) -> None:
        self._session = session
        self._reports = reports
        self._aggregation = aggregation
        self._storage = storage
        self._enqueue = enqueue
        self._enqueue_fn = enqueue_fn
        self._markdown_render_fn = markdown_render_fn or render_markdown
        self._docx_render_fn = docx_render_fn or render_docx
        self._pdf_render_fn = pdf_render_fn or render_pdf
        self._staging_dir = staging_dir

    # ------------------------------------------------------------------
    # HTTP API operations
    # ------------------------------------------------------------------

    async def request_report(
        self,
        *,
        workspace_id: uuid.UUID,
        created_by: uuid.UUID,
        title: str,
        export_format: ReportFormat,
        items: list[AggregationItem],
    ) -> ReportWithItems:
        """Validate sources, create pending Report, commit, enqueue Celery."""
        if not items:
            raise ReportServiceError(
                "empty_items",
                "items must contain at least one source",
                status_code=422,
            )

        # Fail-fast workspace ownership before insert (aggregation validates each id).
        try:
            await self._aggregation.aggregate(workspace_id=workspace_id, items=items)
        except ReportAggregationError as exc:
            raise ReportServiceError(
                exc.code,
                exc.message,
                status_code=exc.status_code,
            ) from exc

        specs = [
            ReportItemSpec(
                source_type=item.source_type
                if isinstance(item.source_type, ReportSourceType)
                else ReportSourceType(str(item.source_type)),
                source_id=item.source_id,
                order_index=item.order_index,
            )
            for item in items
        ]

        outcome = await self._reports.create_pending(
            workspace_id=workspace_id,
            created_by=created_by,
            title=title.strip(),
            format_=export_format,
            items=specs,
        )
        await self._session.commit()

        try:
            self._enqueue_report(outcome.report.id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("report_enqueue_failed", report_id=str(outcome.report.id))
            await self._reports.mark_failed(report_id=outcome.report.id)
            await self._session.commit()
            raise ReportServiceError(
                "enqueue_failed",
                "Failed to schedule report generation",
                status_code=503,
            ) from exc

        refreshed = await self._reports.get(
            workspace_id=workspace_id,
            report_id=outcome.report.id,
        )
        return refreshed or outcome

    async def process_report(self, report_id: uuid.UUID) -> Report | None:
        """Aggregate → render → MinIO upload → status=ready (or failed).

        Idempotent:
          - missing → None
          - not pending → return row unchanged
        """
        row = await self._reports.get_by_id(report_id)
        if row is None:
            logger.info("report_process_missing", report_id=str(report_id))
            return None
        if row.status != ReportStatus.pending:
            logger.info(
                "report_process_skip_status",
                report_id=str(report_id),
                status=row.status.value,
            )
            return row

        item_rows = await self._reports.list_items(report_id)
        agg_items = [
            AggregationItem(
                source_type=item.source_type,
                source_id=item.source_id,
                order_index=item.order_index,
            )
            for item in item_rows
        ]

        try:
            blocks = await self._aggregation.aggregate(
                workspace_id=row.workspace_id,
                items=agg_items,
            )
            object_key = self._render_and_upload(
                report=row,
                blocks=blocks,
            )
            updated = await self._reports.mark_ready(
                report_id=row.id,
                file_path=object_key,
            )
            if not updated:
                logger.warning("report_mark_ready_race", report_id=str(report_id))
            refreshed = await self._reports.get_by_id(report_id)
            return refreshed
        except Exception as exc:  # noqa: BLE001 — worker marks failed; no reports.error column
            # Schema confirmation: reports (v1 / ERD / OpenAPI) has no ``error`` column.
            # Persist status=failed only; full detail goes to structured logs.
            logger.exception(
                "report_process_failed",
                report_id=str(report_id),
                error=str(exc),
            )
            await self._reports.mark_failed(report_id=report_id)
            refreshed = await self._reports.get_by_id(report_id)
            return refreshed

    async def list_reports(
        self,
        *,
        workspace_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> list[ReportWithItems]:
        offset = (max(1, page) - 1) * max(1, page_size)
        return await self._reports.list_for_workspace(
            workspace_id=workspace_id,
            offset=offset,
            limit=page_size,
        )

    async def get_report(
        self,
        *,
        workspace_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> ReportWithItems:
        row = await self._reports.get(workspace_id=workspace_id, report_id=report_id)
        if row is None:
            raise ReportServiceError(
                "not_found",
                "Report not found",
                status_code=404,
            )
        return row

    async def comparison_preview(
        self,
        row: ReportWithItems,
    ) -> dict[str, Any] | None:
        """Structured comparison preview for GET detail. Never generates files."""
        comparison_item = next(
            (
                item
                for item in row.items
                if (
                    item.source_type is ReportSourceType.comparison
                    or str(item.source_type) == ReportSourceType.comparison.value
                )
            ),
            None,
        )
        if comparison_item is None:
            return None
        preview_fn = getattr(self._aggregation, "preview_comparison", None)
        if preview_fn is None:
            return None
        try:
            return await preview_fn(
                workspace_id=row.report.workspace_id,
                comparison_id=comparison_item.source_id,
            )
        except Exception:
            logger.exception(
                "comparison_preview_failed",
                report_id=str(row.report.id),
            )
            return None

    async def delete_report(
        self,
        *,
        workspace_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> None:
        deleted = await self._reports.delete(
            workspace_id=workspace_id,
            report_id=report_id,
        )
        if deleted is None:
            raise ReportServiceError(
                "not_found",
                "Report not found",
                status_code=404,
            )
        if deleted.file_path:
            try:
                self._storage.delete_object(deleted.file_path)
            except Exception:  # noqa: BLE001 — best-effort physical cleanup
                logger.exception(
                    "report_file_delete_failed",
                    report_id=str(report_id),
                    file_path=deleted.file_path,
                )
        await self._session.commit()

    async def export_report(
        self,
        *,
        workspace_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> ReportExportPayload:
        wrapped = await self.get_report(workspace_id=workspace_id, report_id=report_id)
        report = wrapped.report
        if report.status != ReportStatus.ready:
            raise ReportServiceError(
                "not_ready",
                f"Report is not ready for export (status={report.status.value})",
                status_code=409,
            )
        if not report.file_path:
            raise ReportServiceError(
                "file_missing",
                "Report is ready but file_path is empty",
                status_code=409,
            )
        try:
            data = self._storage.download_bytes(report.file_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "report_export_download_failed",
                report_id=str(report_id),
                file_path=report.file_path,
            )
            raise ReportServiceError(
                "file_unavailable",
                "Failed to download report file",
                status_code=503,
            ) from exc

        filename = Path(report.file_path).name
        return ReportExportPayload(
            data=data,
            content_type=CONTENT_TYPES[report.format],
            filename=filename,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _enqueue_report(self, report_id: uuid.UUID) -> None:
        if not self._enqueue:
            return
        if self._enqueue_fn is not None:
            self._enqueue_fn(report_id)
            return
        from app.workers.reports import generate_report as generate_report_task

        generate_report_task.delay(str(report_id))

    def _render_and_upload(
        self,
        *,
        report: Report,
        blocks: list[AggregatedReportBlock],
    ) -> str:
        fmt = report.format
        kwargs: dict[str, Any] = {
            "report_title": report.title,
            "report_id": report.id,
            "workspace_id": report.workspace_id,
            "output_dir": self._staging_dir,
        }

        if fmt is ReportFormat.markdown:
            result = self._markdown_render_fn(blocks, **kwargs)
            local_path = result.local_path
            object_key = result.object_key
            content_type = CONTENT_TYPES[ReportFormat.markdown]
        elif fmt is ReportFormat.docx:
            result = self._docx_render_fn(blocks, **kwargs)
            local_path = result.local_path
            object_key = result.object_key
            content_type = CONTENT_TYPES[ReportFormat.docx]
        elif fmt is ReportFormat.pdf:
            md = self._markdown_render_fn(blocks, **kwargs)
            pdf = self._pdf_render_fn(md.markdown, **kwargs)
            local_path = pdf.local_path
            object_key = pdf.object_key
            content_type = CONTENT_TYPES[ReportFormat.pdf]
        else:
            raise ReportServiceError(
                "unsupported_format",
                f"Unsupported export_format: {fmt!r}",
                status_code=400,
            )

        data = Path(local_path).read_bytes()
        if not data:
            raise ReportServiceError(
                "empty_render",
                "Renderer produced an empty file",
                status_code=500,
            )
        self._storage.upload_bytes(
            object_key=object_key,
            data=data,
            content_type=content_type.split(";")[0].strip(),
        )
        # Best-effort cleanup of local staging file
        try:
            Path(local_path).unlink(missing_ok=True)
        except OSError:
            logger.warning("report_staging_cleanup_failed", path=str(local_path))
        return object_key


def report_file_url(*, workspace_id: uuid.UUID, report_id: uuid.UUID, status: ReportStatus) -> str | None:
    """OpenAPI file_url: export route when ready; else null."""
    if status != ReportStatus.ready:
        return None
    return f"/workspaces/{workspace_id}/reports/{report_id}/export"
