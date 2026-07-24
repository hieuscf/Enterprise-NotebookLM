# =============================================================================
# File: session.py
# Module/Service: Database
# Layer: Repository
# Purpose: Async SQLAlchemy engine and session factory skeleton.
# Responsibilities:
#   - Create async engine from DATABASE_URL
#   - Yield AsyncSession for dependency injection (wired fully in later steps)
# Dependencies:
#   - SQLAlchemy asyncio, asyncpg, DATABASE_URL env
# Public Exports:
#   - async_session_factory, get_db_session, engine
# Database/Table: N/A
# Related Modules: app.db.base, app.core (config Step 2+)
# Important Notes: Phase 1.1 skeleton — no business queries yet.
# =============================================================================

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://notebooklm:notebooklm@localhost:5432/notebooklm",
)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async DB session (FastAPI Depends-ready)."""
    async with async_session_factory() as session:
        yield session
