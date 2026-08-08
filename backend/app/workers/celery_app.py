# =============================================================================
# File: celery_app.py
# Module/Service: Pipeline Worker + Scheduled Jobs
# Layer: Worker
# Purpose: Celery application for document pipeline and maintenance tasks.
# Responsibilities:
#   - Define Celery app bound to Redis broker/backend
#   - Include pipeline + query_cache cleanup modules
#   - Register Celery Beat schedule from Settings (no hardcoded interval)
# Dependencies:
#   - Celery, Redis (via Docker Compose), app.core.config.Settings
# Public Exports:
#   - celery_app
# Database/Table: N/A
# Related Modules: app.workers.pipeline, app.workers.summaries,
#   app.workers.extractions, app.workers.comparisons, app.tasks.cleanup_expired_cache
# Important Notes:
#   - Prefer LLM calls from backend-api; documented exceptions: graph_extraction
#     (ingestion), generate_summary (FR6), generate_extraction (FR7),
#     generate_comparison (FR8).
# =============================================================================

from __future__ import annotations

import os
from datetime import timedelta

from celery import Celery

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

# Fallback only when Settings / env cannot be read at import time.
_DEFAULT_CLEANUP_INTERVAL_MINUTES = 60


def _cleanup_interval_minutes() -> int:
    """Read cleanup interval from env/Settings without hardcoding Beat period."""
    raw = os.getenv("QUERY_CACHE_CLEANUP_INTERVAL_MINUTES")
    if raw is not None and raw.strip():
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    try:
        from app.core.config import get_settings

        return max(1, int(get_settings().query_cache_cleanup_interval_minutes))
    except Exception:  # noqa: BLE001 — Celery boot must not fail on settings load
        return _DEFAULT_CLEANUP_INTERVAL_MINUTES


_CLEANUP_MINUTES = _cleanup_interval_minutes()
# Drop queued duplicates if a prior tick is still pending when the next fires.
_CLEANUP_TASK_EXPIRES_SECONDS = max(60, (_CLEANUP_MINUTES * 60) - 30)

celery_app = Celery(
    "enterprise_notebooklm",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "app.workers.pipeline",
        "app.workers.previews",
        "app.workers.summaries",
        "app.workers.extractions",
        "app.workers.comparisons",
        "app.tasks.cleanup_expired_cache",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "cleanup-expired-query-cache": {
            "task": "cleanup_expired_query_cache",
            "schedule": timedelta(minutes=_CLEANUP_MINUTES),
            "options": {"expires": _CLEANUP_TASK_EXPIRES_SECONDS},
        },
    },
)
