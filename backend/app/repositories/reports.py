# =============================================================================
# File: reports.py
# Module/Service: Report Service (FR9)
# Layer: Repository
# Purpose: Async data access for reports + report_items (UC8).
# Responsibilities:
#   - Create pending Report + ReportItem rows; update ready/failed
#   - Workspace-scoped list / get / delete; worker get_by_id
# Dependencies:
#   - SQLAlchemy AsyncSession; artifacts models
# Public Exports:
#   - ReportRepository, ReportWithItems
# Database/Table: reports, report_items
# Related Modules: app.services.report_service, app.workers.reports
# Important Notes:
#   - Always filter by workspace_id for HTTP multi-tenant isolation.
#   - Schema v1 has no reports.error column — failures use status=failed + logs.
# =============================================================================

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifacts import Report, ReportItem
from app.models.enums import ReportFormat, ReportSourceType, ReportStatus


@dataclass(frozen=True, slots=True)
class ReportItemSpec:
    source_type: ReportSourceType
    source_id: uuid.UUID
    order_index: int


@dataclass(frozen=True, slots=True)
class ReportWithItems:
    report: Report
    items: list[ReportItem]


class ReportRepository:
    """Postgres data access for FR9 reports."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_pending(
        self,
        *,
        workspace_id: uuid.UUID,
        created_by: uuid.UUID,
        title: str,
        format_: ReportFormat,
        items: list[ReportItemSpec],
    ) -> ReportWithItems:
        row = Report(
            workspace_id=workspace_id,
            created_by=created_by,
            title=title,
            format=format_,
            status=ReportStatus.pending,
            file_path=None,
        )
        self._session.add(row)
        await self._session.flush()

        item_rows: list[ReportItem] = []
        for spec in items:
            item = ReportItem(
                report_id=row.id,
                source_type=spec.source_type,
                source_id=spec.source_id,
                order_index=spec.order_index,
            )
            self._session.add(item)
            item_rows.append(item)
        await self._session.flush()
        return ReportWithItems(report=row, items=item_rows)

    async def get_by_id(self, report_id: uuid.UUID) -> Report | None:
        """Load by primary key (Celery worker — no workspace filter)."""
        return await self._session.get(Report, report_id)

    async def get(
        self,
        *,
        workspace_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> ReportWithItems | None:
        stmt = select(Report).where(
            Report.id == report_id,
            Report.workspace_id == workspace_id,
        )
        row = await self.get_row(workspace_id=workspace_id, report_id=report_id)
        if row is None:
            return None
        return ReportWithItems(report=row, items=await self._list_items(row.id))

    async def get_row(
        self,
        *,
        workspace_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> Report | None:
        """Workspace-scoped report row only — no items / comparison payload."""
        stmt = select(Report).where(
            Report.id == report_id,
            Report.workspace_id == workspace_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_for_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[ReportWithItems]:
        stmt = (
            select(Report)
            .where(Report.workspace_id == workspace_id)
            .order_by(Report.created_at.desc())
            .offset(max(0, offset))
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = list((await self._session.execute(stmt)).scalars().all())
        return [
            ReportWithItems(report=row, items=await self._list_items(row.id)) for row in rows
        ]

    async def list_items(self, report_id: uuid.UUID) -> list[ReportItem]:
        return await self._list_items(report_id)

    async def mark_ready(
        self,
        *,
        report_id: uuid.UUID,
        file_path: str,
    ) -> bool:
        """pending → ready. Returns False if row missing or not pending."""
        stmt = (
            update(Report)
            .where(Report.id == report_id, Report.status == ReportStatus.pending)
            .values(status=ReportStatus.ready, file_path=file_path)
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)

    async def mark_failed(self, *, report_id: uuid.UUID) -> bool:
        """pending → failed. Schema v1 has no error column — message goes to logs."""
        stmt = (
            update(Report)
            .where(Report.id == report_id, Report.status == ReportStatus.pending)
            .values(status=ReportStatus.failed, file_path=None)
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount)

    async def delete(
        self,
        *,
        workspace_id: uuid.UUID,
        report_id: uuid.UUID,
    ) -> Report | None:
        """Delete report (+ cascaded items). Returns deleted row snapshot or None."""
        wrapped = await self.get(workspace_id=workspace_id, report_id=report_id)
        if wrapped is None:
            return None
        await self._session.execute(
            delete(Report).where(
                Report.id == report_id,
                Report.workspace_id == workspace_id,
            )
        )
        return wrapped.report

    async def _list_items(self, report_id: uuid.UUID) -> list[ReportItem]:
        stmt = (
            select(ReportItem)
            .where(ReportItem.report_id == report_id)
            .order_by(ReportItem.order_index.asc())
        )
        return list((await self._session.execute(stmt)).scalars().all())
