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
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
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

    # FR12 — Bootstrap Platform Manage (optional). On startup, if this email
    # matches an existing user, set users.platform_role = manage. Never creates
    # accounts or passwords; never promotes workspace admins automatically.
    bootstrap_manage_email: str | None = Field(
        default=None,
        description="Optional email to promote to platform_role=manage at startup",
    )

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

    # FR4 — Chat answer / rewrite LLM provider (embedding stays EMBEDDING_*).
    # CHAT_LLM_PROVIDER: anthropic | openai | gemini (gemini reserved / not wired yet).
    # Accepts aliases like "gpt" / "gpt-5" → openai (normalized in chat_llm).
    chat_llm_provider: str = "anthropic"
    openai_api_key: str | None = None
    openai_api_base: str = "https://api.openai.com/v1"
    openai_chat_model: str = "gpt-5"
    openai_chat_strong_model: str | None = None  # defaults to openai_chat_model
    # gpt-5 / o-series are reasoning models: at the API default ("medium")
    # effort, hidden reasoning tokens can consume the entire completion
    # budget and return an EMPTY message with finish_reason="length" (see
    # app.adapters.openai_chat). These structured extraction calls (answer +
    # rewrite) do not need deep reasoning, so default to "minimal" — override
    # via OPENAI_REASONING_EFFORT if a future model requires a different tier.
    openai_reasoning_effort: str = "minimal"
    # Reserved for later Gemini adapter (not used until provider=gemini is implemented).
    google_api_key: str | None = None
    gemini_chat_model: str = "gemini-2.5-pro"

    # FR2 Step 3 (v3) — Document Understanding parser selection.
    # NOT an LLM Provider call: LlamaParse is a standalone SaaS, billed separately
    # from Anthropic. Only celery-worker talks to it (see System_Architecture note 3).
    # Set DOCUMENT_PARSER=local for offline dev/CI; llamaparse requires LLAMAPARSE_API_KEY.
    document_parser: Literal["llamaparse", "local"] = "llamaparse"
    llamaparse_api_key: str | None = None
    llamaparse_base_url: str = "https://api.cloud.llamaindex.ai"
    # Client-side wall-clock polling budget per submitted job (not an HTTP-only timeout).
    llamaparse_timeout_seconds: int = 120
    # Per-HTTP-request retries (upload/create/poll). Poll-budget expiry does NOT
    # re-submit a new LlamaParse job — see LlamaParseClient._parse_once.
    llamaparse_max_retries: int = 3
    llamaparse_retry_min_wait: float = 1.0
    llamaparse_retry_max_wait: float = 30.0
    llamaparse_cb_failure_threshold: int = 5
    llamaparse_cb_reset_timeout: int = 60
    llamaparse_cb_success_threshold: int = 1
    # fast tier cannot return markdown/items — keep cost_effective or higher.
    llamaparse_tier: Literal[
        "cost_effective",
        "balanced",
        "premium"
    ] = "cost_effective"
    llamaparse_poll_interval_seconds: float = 2.0
    # When DOCUMENT_PARSER=llamaparse: on client poll timeout / 5xx / circuit open,
    # fall back to local OCR instead of failing the whole pipeline.
    # Auth / quota / unsupported-file errors never fall back.
    llamaparse_fallback_to_local_ocr: bool = True

    # FR2 Step 3 — OCR language detection + optional scanned-PDF image OCR (P3)
    ocr_language_detection_enabled: bool = True
    ocr_language_detect_per_segment: bool = False  # doc-level default keeps overhead << 10%
    ocr_language_min_chars: int = 40
    ocr_language_timeout_seconds: float = 0.25
    enable_image_ocr: bool = False  # ENABLE_IMAGE_OCR — scanned PDF via Tesseract
    image_ocr_dpi: int = 200
    image_ocr_max_pages: int = 50
    image_ocr_timeout_seconds: int = 30
    image_ocr_lang: str = "eng+vie"
    # Optional absolute path to tesseract.exe (Windows default auto-detected if empty)
    tesseract_cmd: str | None = None
    # Optional TESSDATA_PREFIX override (folder containing *.traineddata)
    tessdata_prefix: str | None = None

    # FR3 — Hybrid Retrieval (0 LLM). Timeouts / limits from env — never hardcode in services.
    retrieval_vector_timeout_seconds: float = 2.0
    retrieval_bm25_timeout_seconds: float = 2.0
    retrieval_graph_timeout_seconds: float = 2.0
    retrieval_per_source_top_k: int = 20
    retrieval_max_rerank_candidates: int = 100
    retrieval_snippet_max_chars: int = 500
    # FR3 — Search API: drop weak hits before UI (rerank score threshold).
    search_min_score: float = 0.6
    # heuristic = token-overlap (CI/local, no model download); cross_encoder = sentence-transformers
    reranker_backend: Literal["heuristic", "cross_encoder"] = "heuristic"
    reranker_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # FR4/FR3 — Context Assembly (0 LLM; RAG answer-quality P1). Bounded
    # contextual expansion + grouping BEFORE Prompt Construction — see
    # app/services/chat/context_assembly.py. Never blindly include whole docs.
    context_assembly_enabled: bool = True
    context_neighbor_window: int = 1
    context_max_neighbor_seeds: int = 8
    context_max_chunks: int = 24
    context_coverage_min_sections: int = 3
    context_coverage_max_chunks: int = 5

    # FR14 — Confidence Engine (0 LLM). Tunables for post-rerank complex-route gate.
    # Consumed by app.services.retrieval.confidence_engine.build_confidence_config.
    confidence_relevance_threshold: float = 0.65
    confidence_high_threshold: float = 0.65
    confidence_weight_top_score: float = 0.55
    confidence_weight_score_spread: float = 0.35
    confidence_weight_candidate_count: float = 0.10
    confidence_candidate_count_cap: int = 3

    # FR14 — Event Policy Engine heuristics (0 LLM).
    event_policy_ambiguous_max_tokens: int = 5
    event_policy_ambiguous_score_spread_max: float = 0.08
    event_policy_multi_hop_min_doc_diversity: int = 2
    event_policy_multi_hop_top_k: int = 5

    # FR14 — Rewrite Agent (Haiku-tier only; never Sonnet for rewrite).
    rewrite_agent_model: str = "claude-3-5-haiku-latest"
    # 512 (not 256): with a reasoning-tier model (OpenAI provider) even
    # "minimal" reasoning_effort can use a small non-zero token budget before
    # the visible {"rewritten_query": ...} JSON — 256 left ~0 room and caused
    # empty completions (see openai_reasoning_effort docstring above).
    rewrite_agent_max_tokens: int = 512
    rewrite_agent_timeout_seconds: float = 30.0

    # FR14 — Graph Agent Neo4j expansion depth (1–2 only).
    graph_agent_max_hops: int = 2

    # FR4 Part 2 — Answer LLM model tiering (Prompt Construction). Config-only;
    # never hardcode model ids in services. agent_force_strong_model overrides
    # to the strong model when any Micro Agent ran on the complex path.
    chat_answer_light_model: str = "claude-3-5-haiku-latest"
    chat_answer_strong_model: str = "claude-sonnet-4-20250514"
    chat_agent_force_strong_model: bool = True
    chat_answer_max_tokens: int = 4096
    chat_answer_temperature: float = 0.0
    chat_answer_top_p: float = 1.0
    chat_answer_timeout_seconds: float = 120.0
    # Approximate USD / 1M tokens for cost_usd estimates (observability).
    chat_answer_light_input_usd_per_mtok: float = 0.25
    chat_answer_light_output_usd_per_mtok: float = 1.25
    chat_answer_strong_input_usd_per_mtok: float = 3.0
    chat_answer_strong_output_usd_per_mtok: float = 15.0
    # Context windows (tokens) for prompt budgeting — chat + FR6 summary share these.
    chat_answer_light_context_window: int = 200_000
    chat_answer_strong_context_window: int = 200_000
    # Token-chunk size when emitting SSE after structured generation completes.
    chat_sse_token_chunk_chars: int = 24

    # FR6 — AI Summary (reuses chat LLM provider + model tiering above).
    summary_max_output_tokens: int = 4096
    summary_timeout_seconds: float = 120.0
    # Reserve this many tokens for system/style instructions + completion budget.
    summary_prompt_reserve_tokens: int = 4_096

    # FR7 — Information Extraction (reuses chat LLM + model tiering; entities reuse graph).
    extraction_max_output_tokens: int = 4096
    extraction_timeout_seconds: float = 120.0
    extraction_prompt_reserve_tokens: int = 4_096

    # FR8 — Multi-document Comparison (strong model / complex query; 1 LLM call).
    comparison_max_output_tokens: int = 4096
    comparison_timeout_seconds: float = 120.0
    comparison_prompt_reserve_tokens: int = 4_096
    # Max chunks per document when no completed summary exists (topic-ranked).
    comparison_top_chunks_per_document: int = 8
    # CMP-16 — optional clause-pipeline explanation budget (FR8 similarities LLM is separate).
    contract_comparison_max_llm_calls: int = 8

    # FR11 — Query Router (0 LLM). Thresholds consumed by app.config.router_rules.
    query_cache_similarity_threshold: float = 0.92
    # FR11 — Query Cache lifecycle (write-back + Celery Beat cleanup).
    query_cache_default_ttl_seconds: int = 86_400  # 24h
    # Celery Beat interval for ``cleanup_expired_query_cache`` (minutes).
    query_cache_cleanup_interval_minutes: int = 60
    # Max rows deleted per DELETE statement (batched to avoid long table locks).
    query_cache_cleanup_batch_size: int = 1000
    # Semantic cache: Qdrant Top-K candidates before per-entry threshold filter.
    query_cache_semantic_top_k: int = 5
    query_router_factoid_confidence_threshold: float = 0.75
    query_router_minimum_factoid_score: float = 0.70
    query_router_maximum_factoid_length: int = 80
    query_router_factoid_top_k: int = 1
    # FR11 — Query Classifier (rule + embedding centroid; 0 LLM).
    query_router_classifier_confidence_threshold: float = 0.12
    query_router_classifier_margin_threshold: float = 0.03
    query_router_classifier_embedding_dimension: int = 256


@lru_cache
def get_settings() -> Settings:
    return Settings()
