# =============================================================================
# File: workspaces.py
# Module/Service: Workspace Service
# Layer: Repository
# Purpose: Data access for the workspaces table (read for RBAC demo).
# Responsibilities:
#   - Fetch workspace by id
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.identity.Workspace
# Public Exports:
#   - WorkspaceRepository
# Database/Table: workspaces
# Related Modules: app.api.workspaces
# Important Notes: Phase 1.2 — get_by_id only; CRUD writes land in 1.3.
# =============================================================================

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Workspace


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, workspace_id: uuid.UUID) -> Workspace | None:
        stmt = select(Workspace).where(Workspace.id == workspace_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
