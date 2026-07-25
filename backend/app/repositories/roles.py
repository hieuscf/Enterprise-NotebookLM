# =============================================================================
# File: roles.py
# Module/Service: Workspace Service / Auth
# Layer: Repository
# Purpose: Data access for the roles lookup table (admin/editor/viewer).
# Responsibilities:
#   - Fetch role by RoleName (needed when inserting workspace_members)
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.identity.Role
# Public Exports:
#   - RoleRepository
# Database/Table: roles
# Related Modules: app.services.workspaces, app.repositories.workspace_members
# Important Notes: Roles are seeded by migration a1b2c3d4e5f6; do not invent names.
# =============================================================================

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RoleName
from app.models.identity import Role


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_name(self, name: RoleName) -> Role | None:
        stmt = select(Role).where(Role.name == name).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
