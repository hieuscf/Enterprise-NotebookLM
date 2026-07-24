# =============================================================================
# File: env.py
# Module/Service: Alembic
# Layer: Schema
# Purpose: Alembic runtime environment — bind metadata and DATABASE_URL.
# Responsibilities:
#   - Load all ORM models into Base.metadata
#   - Convert async DATABASE_URL to sync psycopg2 URL for migrations
#   - Run online/offline migration modes
# Dependencies:
#   - Alembic, SQLAlchemy, app.db.base, app.models
# Public Exports:
#   - run_migrations_offline, run_migrations_online
# Database/Table: All schema v2 tables
# Related Modules: alembic.ini, app.models
# Important Notes: Do not invent tables outside official design docs.
# =============================================================================

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401 — register all models on Base.metadata
from alembic import context
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_sync_database_url() -> str:
    url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://notebooklm:notebooklm@localhost:5432/notebooklm",
    )
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def run_migrations_offline() -> None:
    url = get_sync_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_sync_database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
