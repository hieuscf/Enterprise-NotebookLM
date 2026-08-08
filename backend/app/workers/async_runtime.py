# =============================================================================
# File: async_runtime.py
# Module/Service: Pipeline Worker / Celery
# Layer: Worker
# Purpose: Safe asyncio.run wrapper for Celery tasks that use AsyncEngine.
# Responsibilities:
#   - Dispose module-level asyncpg pool before/after each asyncio.run
#   - Avoid "Future attached to a different loop" / "Event loop is closed"
# Dependencies:
#   - asyncio, app.db.session.engine
# Public Exports:
#   - run_celery_async
# Database/Table: N/A
# Related Modules: app.workers.summaries, app.workers.extractions
# Important Notes:
#   - Prefork Celery + module-level create_async_engine shares connections
#     across asyncio.run() loops unless the pool is disposed each task.
#   - Pipeline stages use sync SQLAlchemy and do not need this helper.
# =============================================================================

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_celery_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` under ``asyncio.run`` with a clean AsyncEngine pool.

    Each Celery task that calls ``asyncio.run`` gets a new event loop. The
    process-global AsyncEngine keeps pooled asyncpg connections bound to the
    previous (closed) loop, which raises RuntimeError on the next task.
    Disposing before and after forces fresh connections on the active loop.
    """

    async def _wrapped() -> T:
        from app.db.session import engine

        await engine.dispose()
        try:
            return await coro
        finally:
            await engine.dispose()

    return asyncio.run(_wrapped())
