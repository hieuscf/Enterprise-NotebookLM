# =============================================================================
# File: __init__.py
# Module/Service: Database
# Layer: Repository
# Purpose: Package marker for SQLAlchemy engine, session, and declarative base.
# Responsibilities:
#   - Expose shared DB session factory and Base metadata for models/Alembic
# Dependencies:
#   - SQLAlchemy, asyncpg
# Public Exports:
#   - Base (from app.db.base), get_db_session (from app.db.session)
# Database/Table: All schema v2 tables (Step 3)
# Related Modules: app.models, alembic/
# Important Notes: Phase 1.1 skeleton — full wiring with config in later steps.
# =============================================================================

from app.db.base import Base
from app.db.session import get_db_session

__all__ = ["Base", "get_db_session"]
