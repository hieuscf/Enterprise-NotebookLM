# =============================================================================
# File: main.py
# Module/Service: Backend API System
# Layer: Presentation
# Purpose: FastAPI application entrypoint for Enterprise NotebookLM.
# Responsibilities:
#   - Create and configure the FastAPI app instance
#   - Expose health/readiness endpoints for Docker and orchestration
#   - Mount routers from app.api (added in later phases)
# Dependencies:
#   - FastAPI
# Public Exports:
#   - app
# Database/Table: N/A
# Related Modules: app.api, app.core, app.db
# Important Notes: Phase 1.1 skeleton only — no business routers yet.
# =============================================================================

from fastapi import FastAPI

app = FastAPI(
    title="Enterprise NotebookLM API",
    version="0.1.0",
    description="Backend API System — Phase 1.1 infrastructure skeleton.",
)


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    """Liveness probe for Docker / orchestrators."""
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
async def ready() -> dict[str, str]:
    """Readiness probe placeholder (DB checks added after Alembic/Step 3)."""
    return {"status": "ready"}
