# =============================================================================
# File: celery_app.py
# Module/Service: Pipeline Worker
# Layer: Worker
# Purpose: Celery application skeleton for document pipeline workers.
# Responsibilities:
#   - Define Celery app instance bound to Redis broker/backend
#   - Autodiscover tasks under app.workers (tasks added in later phases)
# Dependencies:
#   - Celery, Redis (via Docker Compose)
# Public Exports:
#   - celery_app
# Database/Table: N/A
# Related Modules: app.workers, docker-compose.yml
# Important Notes: Phase 1.1 skeleton only — no pipeline stage tasks yet.
# =============================================================================

import os

from celery import Celery

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery_app = Celery(
    "enterprise_notebooklm",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
