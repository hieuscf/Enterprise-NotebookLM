# =============================================================================
# File: sync_session.py
# Module/Service: Database / Pipeline Worker
# Layer: Repository
# Purpose: Synchronous SQLAlchemy engine/session for Celery workers (FR2).
# Responsibilities:
#   - Convert async DATABASE_URL (asyncpg) to psycopg2 sync URL
#   - Provide context-managed Session for pipeline stage persistence
# Dependencies:
#   - SQLAlchemy, psycopg2, DATABASE_URL env
# Public Exports:
#   - sync_engine, sync_session_factory, get_sync_session, to_sync_database_url
# Database/Table: N/A
# Related Modules: app.workers.pipeline, app.db.session
# Important Notes: Celery tasks are sync — do not use AsyncSession here.
# =============================================================================

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def to_sync_database_url(url: str) -> str:
    """Map async SQLAlchemy URL to a sync driver URL for Celery workers."""
    if "+asyncpg" in url:
        return url.replace("+asyncpg", "+psycopg2", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


SYNC_DATABASE_URL = to_sync_database_url(
    os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://notebooklm:notebooklm@localhost:5432/notebooklm",
    )
)

sync_engine = create_engine(SYNC_DATABASE_URL, pool_pre_ping=True)
sync_session_factory = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)


@contextmanager
def get_sync_session() -> Generator[Session, None, None]:
    """Yield a sync Session; commit on success, rollback on error."""
    session = sync_session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
