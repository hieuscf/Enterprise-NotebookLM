# =============================================================================
# File: config.py
# Module/Service: Core / Observability Module
# Layer: Adapter
# Purpose: Application settings loaded from environment variables.
# Responsibilities:
#   - Centralize APP_ENV, logging, and OpenTelemetry exporter settings
# Dependencies:
#   - pydantic-settings
# Public Exports:
#   - Settings, get_settings
# Database/Table: N/A
# Related Modules: app.core.logging, app.core.tracing, app.main
# Important Notes: Empty OTEL_EXPORTER_OTLP_ENDPOINT must be treated as "disabled".
# =============================================================================

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"

    otel_service_name: str = "enterprise-notebooklm-backend"
    otel_exporter_otlp_endpoint: str | None = None
    otel_console_exporter: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
