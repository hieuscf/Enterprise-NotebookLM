# =============================================================================
# File: celery_app.py
# Module/Service: Pipeline Worker
# Layer: Worker
# Purpose: Celery application for document pipeline workers (FR2).
# Responsibilities:
#   - Define Celery app bound to Redis broker/backend
#   - Include pipeline task module
# Dependencies:
#   - Celery, Redis (via Docker Compose)
# Public Exports:
#   - celery_app
# Database/Table: N/A
# Related Modules: app.workers.pipeline, docker-compose.yml
# Important Notes: Workers must NOT call LLM Provider (Anthropic).
# =============================================================================

import os

from celery import Celery

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

celery_app = Celery(
    "enterprise_notebooklm",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["app.workers.pipeline"],
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
)
