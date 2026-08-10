# =============================================================================
# File: bootstrap_manage.py
# Module/Service: Auth Service / Platform RBAC (FR12)
# Layer: Service
# Purpose: Idempotent startup promotion of BOOTSTRAP_MANAGE_EMAIL to Manage.
# Responsibilities:
#   - Look up existing user by email (case-insensitive)
#   - Set platform_role=manage when currently NULL
# Dependencies:
#   - UserRepository, Settings, PlatformRole
# Public Exports:
#   - bootstrap_platform_manage
# Database/Table: users
# Related Modules: app.main lifespan, app.core.config
# Important Notes:
#   - Never creates users or passwords.
#   - Never promotes workspace admins automatically.
# =============================================================================

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.enums import PlatformRole
from app.repositories.users import UserRepository

logger = get_logger(__name__)


async def bootstrap_platform_manage(session: AsyncSession, settings: Settings) -> None:
    email = (settings.bootstrap_manage_email or "").strip().lower()
    if not email:
        return

    users = UserRepository(session)
    user = await users.get_by_email_ci(email)
    if user is None:
        logger.warning(
            "bootstrap_manage_user_not_found",
            email=email,
        )
        return

    if user.platform_role == PlatformRole.manage:
        logger.info("bootstrap_manage_already_set", user_id=str(user.id))
        return

    await users.set_platform_role(user, PlatformRole.manage)
    await session.commit()
    logger.info("bootstrap_manage_promoted", user_id=str(user.id), email=email)
