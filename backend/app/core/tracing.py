# =============================================================================
# File: tracing.py
# Module/Service: Observability Module
# Layer: Adapter
# Purpose: OpenTelemetry foundation for FastAPI + SQLAlchemy (FR13).
# Responsibilities:
#   - Initialize TracerProvider; export to OTLP and/or console when configured
#   - Instrument FastAPI app and SQLAlchemy engine safely when OTLP is unset
#   - Expose get_tracer hook for later service spans
# Dependencies:
#   - opentelemetry-*, app.core.config, SQLAlchemy engine
# Public Exports:
#   - setup_tracing, instrument_app, instrument_sqlalchemy_engine, get_tracer,
#     shutdown_tracing
# Database/Table: N/A
# Related Modules: app.main, app.db.session
# Important Notes: Empty OTEL_EXPORTER_OTLP_ENDPOINT must NOT crash startup.
# =============================================================================

from __future__ import annotations

from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Tracer

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_provider: TracerProvider | None = None


def setup_tracing(settings: Settings | None = None) -> TracerProvider:
    """Create and register a global TracerProvider with optional exporters."""
    global _provider
    settings = settings or get_settings()

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment": settings.app_env,
        }
    )
    provider = TracerProvider(resource=resource)

    endpoint = (settings.otel_exporter_otlp_endpoint or "").strip()
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
            )
            logger.info("otel_otlp_exporter_enabled", endpoint=endpoint)
        except Exception:
            # Never fail process startup because of exporter misconfiguration.
            logger.exception("otel_otlp_exporter_setup_failed", endpoint=endpoint)

    if settings.otel_console_exporter:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("otel_console_exporter_enabled")

    if not endpoint and not settings.otel_console_exporter:
        logger.info(
            "otel_exporters_disabled",
            reason="OTEL_EXPORTER_OTLP_ENDPOINT empty and OTEL_CONSOLE_EXPORTER false",
        )

    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def instrument_app(app: Any) -> None:
    """Instrument a FastAPI application for HTTP spans."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    logger.info("otel_fastapi_instrumented")


def instrument_sqlalchemy_engine(engine: Any) -> None:
    """Instrument a SQLAlchemy Engine (use async_engine.sync_engine for asyncio)."""
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    sync_engine = getattr(engine, "sync_engine", engine)
    SQLAlchemyInstrumentor().instrument(engine=sync_engine)
    logger.info("otel_sqlalchemy_instrumented")


def get_tracer(name: str = "enterprise-notebooklm") -> Tracer:
    """Return a tracer for services to create custom spans later."""
    return trace.get_tracer(name)


def shutdown_tracing() -> None:
    """Flush and shut down the tracer provider (app lifespan shutdown)."""
    global _provider
    if _provider is not None:
        _provider.shutdown()
        _provider = None
