# =============================================================================
# File: cleanup_expired_cache.py
# Module/Service: Query Cache Lifecycle (FR11)
# Layer: Worker
# Purpose: Celery Beat job to delete expired query_cache rows in batches.
# Responsibilities:
#   - DELETE FROM query_cache WHERE expires_at < now() (batched LIMIT)
#   - Log deleted_count for FR13 observability; idempotent on re-run
# Dependencies:
#   - Celery, get_sync_session, delete_expired_query_cache_sync, Settings
# Public Exports:
#   - cleanup_expired_query_cache, run_cleanup_expired_query_cache
# Database/Table: query_cache
# Related Modules: app.workers.celery_app (beat_schedule), QueryCacheRepository
# Important Notes:
#   - Sync Session (Celery); hard-delete (no soft-delete column on query_cache).
#   - Relies on index ix_query_cache_expires_at / workspace_id+expires_at.
#   - Interval + batch_size come from Settings — never hard-code.
# =============================================================================

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.repositories.query_cache import (
    DEFAULT_CLEANUP_BATCH_SIZE,
    QueryCacheRepositoryError,
    delete_expired_query_cache_sync,
)
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def run_cleanup_expired_query_cache(
    session: Session,
    *,
    now: datetime | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Execute expired-cache cleanup (testable without Celery broker).

    Args:
        session: Sync SQLAlchemy session.
        now: Optional clock override.
        batch_size: Optional override for DELETE batch size.

    Returns:
        ``{"deleted_count": int, "batch_size": int, "started_at": str,
        "finished_at": str, "duration_ms": int}``.
    """
    settings = get_settings()
    limit = (
        max(1, int(batch_size))
        if batch_size is not None
        else max(1, int(settings.query_cache_cleanup_batch_size or DEFAULT_CLEANUP_BATCH_SIZE))
    )
    started = datetime.now(UTC)
    t0 = time.perf_counter()
    logger.info(
        "query_cache_cleanup_started",
        started_at=started.isoformat(),
        batch_size=limit,
    )
    try:
        deleted = delete_expired_query_cache_sync(
            session, now=now, batch_size=limit
        )
    except QueryCacheRepositoryError:
        logger.exception("query_cache_cleanup_failed", batch_size=limit)
        raise
    except Exception:
        logger.exception("query_cache_cleanup_unexpected_error", batch_size=limit)
        raise

    finished = datetime.now(UTC)
    duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
    payload = {
        "deleted_count": deleted,
        "batch_size": limit,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": duration_ms,
    }
    # FR13 observability — always log how many rows were removed this run.
    logger.info(
        "query_cache_cleanup_finished",
        deleted_count=deleted,
        batch_size=limit,
        duration_ms=duration_ms,
        started_at=payload["started_at"],
        finished_at=payload["finished_at"],
    )
    return payload


@celery_app.task(
    name="cleanup_expired_query_cache",
    bind=True,
    max_retries=3,
    autoretry_for=(QueryCacheRepositoryError,),
    retry_backoff=True,
    retry_jitter=True,
)
def cleanup_expired_query_cache(self) -> dict[str, Any]:  # noqa: ARG001
    """Celery Beat task: delete expired ``query_cache`` rows; return metrics."""
    with get_sync_session() as session:
        return run_cleanup_expired_query_cache(session)
