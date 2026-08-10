# =============================================================================
# File: users.py
# Module/Service: Auth Service
# Layer: Repository
# Purpose: Data access for the users table.
# Responsibilities:
#   - Fetch user by email or id; case-insensitive email lookup
#   - Create / hard-delete users; list users without active membership
#   - Detect RESTRICT FK blockers for permanent delete
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.*
# Public Exports:
#   - UserRepository
# Database/Table: users (+ read-only exists checks on artifact tables)
# Related Modules: app.services.auth, app.services.admin_users
# Important Notes: No business logic (password verify belongs in AuthService).
# =============================================================================

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifacts import Comparison, Extraction, Report, Summary
from app.models.documents import DocumentVersion
from app.models.enums import UserStatus
from app.models.identity import User, WorkspaceMember


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email_ci(self, email: str) -> User | None:
        """Case-insensitive email match (for create uniqueness)."""
        stmt = select(User).where(func.lower(User.email) == email.lower())
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: str,
        status: UserStatus = UserStatus.active,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            status=status,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def delete(self, user: User) -> None:
        await self._session.delete(user)
        await self._session.flush()

    async def list_users_without_active_membership(self) -> list[User]:
        """Active users with no active (non-soft-deleted) workspace membership."""
        active_member = (
            select(WorkspaceMember.id)
            .where(
                WorkspaceMember.user_id == User.id,
                WorkspaceMember.deleted_at.is_(None),
            )
            .correlate(User)
            .exists()
        )
        stmt = (
            select(User)
            .where(User.status == UserStatus.active, ~active_member)
            .order_by(User.email.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_restricting_dependency_tables(self, user_id: uuid.UUID) -> list[str]:
        """Return table names that RESTRICT hard-delete of this user."""
        checks: list[tuple[str, object]] = [
            (
                "document_versions",
                select(DocumentVersion.id)
                .where(DocumentVersion.uploaded_by == user_id)
                .limit(1),
            ),
            (
                "summaries",
                select(Summary.id).where(Summary.created_by == user_id).limit(1),
            ),
            (
                "extractions",
                select(Extraction.id).where(Extraction.created_by == user_id).limit(1),
            ),
            (
                "comparisons",
                select(Comparison.id).where(Comparison.created_by == user_id).limit(1),
            ),
            (
                "reports",
                select(Report.id).where(Report.created_by == user_id).limit(1),
            ),
        ]
        blockers: list[str] = []
        for name, stmt in checks:
            found = (await self._session.execute(stmt)).scalar_one_or_none()
            if found is not None:
                blockers.append(name)
        return blockers
