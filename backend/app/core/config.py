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
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

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

    # FR2 — Object storage / search / vector / graph adapters
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "notebooklm-documents"
    minio_secure: bool = False

    vector_store: str = "qdrant"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "document_chunks"
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index: str = "document_chunks"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "notebooklm"

    # Local / remote embedding (Celery may call Voyage/OpenAI embed APIs; not Anthropic LLM)
    embedding_model_name: str = "local-hash-embedding-v1"
    embedding_dimension: int = 384
    embedding_provider: str = "local"  # local | openai | voyage
    embedding_api_key: str | None = None
    embedding_batch_size: int = 32
    chunk_max_tokens: int = 512
    chunk_overlap_ratio: float = 0.12

    # FR2 Step 5 — Graph Extraction LLM (ONLY ingestion stage with chat LLM cost).
    # Prefer Haiku-class: structured extraction does not need Sonnet/Opus.
    # Default enabled=false so local/CI use heuristic fallback without API key.
    anthropic_api_key: str | None = None
    anthropic_api_base: str = "https://api.anthropic.com"
    graph_llm_enabled: bool = False
    graph_llm_model: str = "claude-3-5-haiku-latest"
    graph_llm_max_tokens: int = 4096
    graph_llm_max_input_chars: int = 100_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
