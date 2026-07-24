# =============================================================================
# File: config.py
# Module/Service: Core / Observability Module
# Layer: Adapter
# Purpose: Application settings loaded from environment variables.
# Responsibilities:
#   - Centralize APP_ENV, logging, OpenTelemetry, JWT, Redis, and DB settings
# Dependencies:
#   - pydantic-settings
# Public Exports:
#   - Settings, get_settings
# Database/Table: N/A
# Related Modules: app.core.logging, app.core.tracing, app.core.security, app.main
# Important Notes: Empty OTEL_EXPORTER_OTLP_ENDPOINT must be treated as "disabled".
#   JWT_SECRET_KEY must be overridden outside local/dev — never hardcode secrets.
# =============================================================================

from functools import lru_cache

from pydantic import Field
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

    database_url: str = "postgresql+asyncpg://notebooklm:notebooklm@localhost:5432/notebooklm"
    redis_url: str = "redis://localhost:6379/0"

    # FR12 — JWT (override JWT_SECRET_KEY in every non-local environment)
    jwt_secret_key: str = Field(
        default="dev-only-change-me-enterprise-notebooklm-jwt",
        description="HMAC secret for JWT signing; set via JWT_SECRET_KEY",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # FR12 — API-layer rate limit per workspace (not LLM call quota; see phase 2).
    rate_limit_requests_per_minute: int = 60
    rate_limit_window_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
