# =============================================================================
# File: cleanup_expired_cache.py
# Module/Service: Query Cache Lifecycle (FR11)
# Layer: Worker
# Purpose: Celery Beat job to delete expired query_cache rows.
# Responsibilities:
#   - DELETE FROM query_cache WHERE expires_at < now()
#   - Return deleted_count for monitoring; idempotent on re-run
# Dependencies:
#   - Celery, get_sync_session, delete_expired_query_cache_sync
# Public Exports:
#   - cleanup_expired_query_cache, run_cleanup_expired_query_cache
# Database/Table: query_cache
# Related Modules: app.workers.celery_app (beat_schedule), QueryCacheRepository
# Important Notes:
#   - Sync Session (Celery); does not load full table into memory.
#   - Relies on index ix_query_cache_expires_at / workspace_id+expires_at.
# =============================================================================

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.repositories.query_cache import (
    QueryCacheRepositoryError,
    delete_expired_query_cache_sync,
)
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def run_cleanup_expired_query_cache(
    session: Session,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Execute expired-cache cleanup (testable without Celery broker).

    Args:
        session: Sync SQLAlchemy session.
        now: Optional clock override.

    Returns:
        ``{"deleted_count": int, "started_at": str, "finished_at": str,
        "duration_ms": int}``.
    """
    started = datetime.now(UTC)
    t0 = time.perf_counter()
    logger.info("query_cache_cleanup_started", started_at=started.isoformat())
    try:
        deleted = delete_expired_query_cache_sync(session, now=now)
    except QueryCacheRepositoryError:
        logger.exception("query_cache_cleanup_failed")
        raise
    except Exception:
        logger.exception("query_cache_cleanup_unexpected_error")
        raise

    finished = datetime.now(UTC)
    duration_ms = max(0, int((time.perf_counter() - t0) * 1000))
    payload = {
        "deleted_count": deleted,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": duration_ms,
    }
    logger.info(
        "query_cache_cleanup_finished",
        deleted_count=deleted,
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
    # Discard late duplicates when a previous run is still queued past interval.
    expires=14 * 60,
)
def cleanup_expired_query_cache(self) -> dict[str, Any]:  # noqa: ARG001
    """Celery task: delete expired ``query_cache`` rows; return metrics dict."""
    with get_sync_session() as session:
        return run_cleanup_expired_query_cache(session)
