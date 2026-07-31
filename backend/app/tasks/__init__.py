# =============================================================================
# File: __init__.py
# Module/Service: Background Tasks
# Layer: Worker
# Purpose: Package marker for non-pipeline Celery tasks.
# Responsibilities:
#   - Namespace for maintenance tasks (query_cache cleanup, …)
# Dependencies:
#   - N/A
# Public Exports:
#   - N/A (import task modules directly to avoid Celery circular imports)
# Database/Table: N/A
# Related Modules: app.tasks.cleanup_expired_cache
# Important Notes: Do not eagerly import Celery task modules here.
# =============================================================================
