# =============================================================================
# File: create_manage_user.py
# Module/Service: Auth Service / Platform RBAC bootstrap
# Layer: Adapter
# Purpose: One-shot CLI to create (or promote) a Platform Manage account locally.
# Responsibilities:
#   - Create user with argon2 password hash if missing
#   - Set users.platform_role = manage
# Dependencies:
#   - app.core.security, app.db.session, app.models.*, sqlalchemy
# Public Exports:
#   - N/A (CLI)
# Database/Table: users
# Related Modules: app.services.bootstrap_manage
# Important Notes: Dev/bootstrap only — do not commit passwords; pass via argv/env.
# =============================================================================

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import async_session_factory
from app.models.enums import PlatformRole, UserStatus
from app.models.identity import User


async def main(email: str, password: str, full_name: str) -> int:
    email_n = email.strip().lower()
    if not email_n or not password:
        print("email and password are required", file=sys.stderr)
        return 2

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == email_n)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                email=email_n,
                password_hash=hash_password(password),
                full_name=full_name.strip() or "Platform Manager",
                status=UserStatus.active,
                platform_role=PlatformRole.manage,
            )
            session.add(user)
            await session.commit()
            print(f"created manage user: {email_n}")
            return 0

        user.password_hash = hash_password(password)
        user.full_name = full_name.strip() or user.full_name
        user.status = UserStatus.active
        user.platform_role = PlatformRole.manage
        await session.commit()
        print(f"updated existing user to manage: {email_n}")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create/promote Platform Manage user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--full-name", default="Platform Manager")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.email, args.password, args.full_name)))
