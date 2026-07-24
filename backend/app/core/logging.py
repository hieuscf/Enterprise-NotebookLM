# =============================================================================
# File: logging.py
# Module/Service: Observability Module
# Layer: Adapter
# Purpose: Configure structlog for JSON application logs (FR13 foundation).
# Responsibilities:
#   - Set up JSON processors with contextvars merge (request_id, workspace_id)
#   - Expose get_logger / bind helpers for services to call later
# Dependencies:
#   - structlog, app.core.config
# Public Exports:
#   - configure_logging, get_logger, bind_log_context, clear_log_context
# Database/Table: N/A
# Related Modules: app.core.middleware, app.main
# Important Notes: Does NOT write pipeline_stage_logs / query_logs — HTTP layer only.
# =============================================================================

from __future__ import annotations

import logging
from typing import Any

import structlog

from app.core.config import Settings, get_settings


def configure_logging(settings: Settings | None = None) -> None:
    """Configure stdlib logging + structlog JSON output."""
    settings = settings or get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", level=level, force=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.EventRenamer("message"),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str | None = None) -> Any:
    """Return a bound structlog logger for modules/services."""
    return structlog.get_logger(name)


def bind_log_context(**kwargs: Any) -> None:
    """Bind key/value pairs into structlog contextvars (request-scoped)."""
    structlog.contextvars.bind_contextvars(**{k: v for k, v in kwargs.items() if v is not None})


def clear_log_context() -> None:
    """Clear request-scoped structlog contextvars."""
    structlog.contextvars.clear_contextvars()
