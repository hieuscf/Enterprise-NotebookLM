# =============================================================================
# File: main.py
# Module/Service: Backend API System
# Layer: Presentation
# Purpose: FastAPI application entrypoint for Enterprise NotebookLM.
# Responsibilities:
#   - Create and configure the FastAPI app instance
#   - Wire structlog request logging and OpenTelemetry instrumentation (FR13)
#   - Mount auth routers (FR12) and health/readiness probes
# Dependencies:
#   - FastAPI, app.api.auth, app.core.*, app.db
# Public Exports:
#   - app
# Database/Table: N/A
# Related Modules: app.api, app.core, app.db
# Important Notes: Observability is foundation-only; no query_logs persistence yet.
# =============================================================================

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.workspaces import router as workspaces_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestLoggingMiddleware
from app.core.tracing import (
    instrument_app,
    instrument_sqlalchemy_engine,
    setup_tracing,
    shutdown_tracing,
)
from app.db.session import engine

settings = get_settings()
configure_logging(settings)
setup_tracing(settings)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    instrument_sqlalchemy_engine(engine)
    logger.info("application_startup", app_env=settings.app_env)
    yield
    shutdown_tracing()
    logger.info("application_shutdown")


app = FastAPI(
    title="Enterprise NotebookLM API",
    version="0.1.0",
    description="Backend API System — Phase 1.2 Auth & RBAC foundation.",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
instrument_app(app)
app.include_router(auth_router)
app.include_router(workspaces_router)


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    """Liveness probe for Docker / orchestrators."""
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
async def ready() -> dict[str, str]:
    """Readiness probe placeholder (DB checks added after Alembic/Step 3)."""
    return {"status": "ready"}
