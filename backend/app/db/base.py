# =============================================================================
# File: base.py
# Module/Service: Database
# Layer: Schema
# Purpose: SQLAlchemy declarative base for all ORM models.
# Responsibilities:
#   - Provide shared DeclarativeBase for app.models and Alembic metadata
# Dependencies:
#   - SQLAlchemy 2.x
# Public Exports:
#   - Base
# Database/Table: N/A (metadata registry)
# Related Modules: app.models, alembic/
# Important Notes: Models are added in Step 3 — do not invent tables here.
# =============================================================================

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for Enterprise NotebookLM ORM models."""
