# =============================================================================
# File: users.py
# Module/Service: Auth Service
# Layer: Repository
# Purpose: Data access for the users table.
# Responsibilities:
#   - Fetch user by email or id
# Dependencies:
#   - SQLAlchemy AsyncSession, app.models.identity.User
# Public Exports:
#   - UserRepository
# Database/Table: users
# Related Modules: app.services.auth
# Important Notes: No business logic (password verify belongs in AuthService).
# =============================================================================

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
