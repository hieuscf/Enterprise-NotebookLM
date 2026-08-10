# =============================================================================
# File: main.py
# Module/Service: Backend API System
# Layer: Presentation
# Purpose: FastAPI application entrypoint for Enterprise NotebookLM.
# Responsibilities:
#   - Create and configure the FastAPI app instance
#   - Wire structlog request logging and OpenTelemetry instrumentation (FR13)
#   - Mount auth, workspace, and document ingestion routers (FR12, FR1, FR2)
# Dependencies:
#   - FastAPI, app.api.*, app.core.*, app.db
# Public Exports:
#   - app
# Database/Table: N/A
# Related Modules: app.api, app.core, app.db
# Important Notes: Observability is foundation-only; no query_logs persistence yet.
# =============================================================================

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import router as admin_router
from app.api.admin_users import router as admin_users_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.comparisons import router as comparisons_router
from app.api.documents import router as documents_router
from app.api.extractions import router as extractions_router
from app.api.reports import router as reports_router
from app.api.search import router as search_router
from app.api.summaries import router as summaries_router
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
from app.db.session import async_session_factory, engine
from app.services.bootstrap_manage import bootstrap_platform_manage

settings = get_settings()
configure_logging(settings)
setup_tracing(settings)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    instrument_sqlalchemy_engine(engine)
    logger.info("application_startup", app_env=settings.app_env)
    if settings.bootstrap_manage_email:
        async with async_session_factory() as session:
            await bootstrap_platform_manage(session, settings)
    yield
    shutdown_tracing()
    logger.info("application_shutdown")


app = FastAPI(
    title="Enterprise NotebookLM API",
    version="0.1.0",
    description="Backend API System — Phase 2 Search (FR3) + Document Ingestion (FR2).",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
instrument_app(app)
app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(chat_router)
app.include_router(summaries_router)
app.include_router(extractions_router)
app.include_router(comparisons_router)
app.include_router(reports_router)
app.include_router(admin_router)
app.include_router(admin_users_router)


@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    """Liveness probe for Docker / orchestrators."""
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
async def ready() -> dict[str, str]:
    """Readiness probe placeholder (DB checks added after Alembic/Step 3)."""
    return {"status": "ready"}
