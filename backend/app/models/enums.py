# =============================================================================
# File: enums.py
# Module/Service: Models
# Layer: Schema
# Purpose: PostgreSQL ENUM value definitions for schema v3.
# Responsibilities:
#   - Centralize all DB enum types used by SQLAlchemy models
# Dependencies:
#   - database-design-enterprise-notebooklm.md, erd-enterprise-notebooklm.mermaid,
#     Enterprise notebooklm openapi.yaml
# Public Exports:
#   - All *Enum classes listed below
# Database/Table: N/A (type definitions only)
# Related Modules: app.models.*
# Important Notes: Values must match docs; do not invent new enum members.
# =============================================================================

import enum


class UserStatus(enum.StrEnum):
    active = "active"
    disabled = "disabled"


class RoleName(enum.StrEnum):
    """Workspace-scoped roles only (workspace_members → roles). Never include manage."""

    admin = "admin"
    editor = "editor"
    viewer = "viewer"


class PlatformRole(enum.StrEnum):
    """Platform-scoped role on users.platform_role (Enterprise Admin Console).

    Ordinary users store NULL — this enum only lists the granted platform value.
    """

    manage = "manage"


class FileType(enum.StrEnum):
    pdf = "pdf"
    docx = "docx"
    xlsx = "xlsx"
    pptx = "pptx"
    txt = "txt"


class DocumentVersionStatus(enum.StrEnum):
    processing = "processing"
    ready = "ready"
    failed = "failed"


class PreviewStatus(enum.StrEnum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class PreviewType(enum.StrEnum):
    pdf = "pdf"
    html = "html"
    image = "image"


class PipelineStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class PipelineStage(enum.StrEnum):
    # Deprecated v2 — retained in DB enum for historical pipeline_stage_logs rows.
    ocr_cleaning = "ocr_cleaning"
    chunking = "chunking"
    # Preview Representation (before AI stages) — Original Document Viewer
    preview_generation = "preview_generation"
    # v3 ingestion stages (preferred for new pipeline runs)
    document_understanding = "document_understanding"
    cleaning_normalize = "cleaning_normalize"
    hierarchical_chunking = "hierarchical_chunking"
    embedding = "embedding"
    graph_extraction = "graph_extraction"
    indexing = "indexing"


class ChunkLayoutType(enum.StrEnum):
    heading = "heading"
    paragraph = "paragraph"
    table = "table"
    list = "list"
    figure_caption = "figure_caption"


class ConfidenceLevel(enum.StrEnum):
    high = "high"
    low = "low"


class AgentType(enum.StrEnum):
    rewrite = "rewrite"
    graph = "graph"
    sql = "sql"


class AgentTriggerReason(enum.StrEnum):
    ambiguous_query = "ambiguous_query"
    multi_hop_reasoning = "multi_hop_reasoning"
    structured_misclassified = "structured_misclassified"


class VectorStore(enum.StrEnum):
    qdrant = "qdrant"
    pgvector = "pgvector"


class MessageRole(enum.StrEnum):
    user = "user"
    assistant = "assistant"


class RouteType(enum.StrEnum):
    cache_hit = "cache_hit"
    metadata = "metadata"
    section_extraction = "section_extraction"
    factoid = "factoid"
    complex = "complex"


class FinishReason(enum.StrEnum):
    stop = "stop"
    length = "length"
    content_filter = "content_filter"
    tool_calls = "tool_calls"


class RetrievalMethod(enum.StrEnum):
    vector = "vector"
    bm25 = "bm25"
    knowledge_graph = "knowledge_graph"
    rerank = "rerank"


class SummaryType(enum.StrEnum):
    """Aligned with OpenAPI Summary.style (by_topic / bullet_points).

    DB column is ``summaries.type``; API contract uses the name ``style``.
    """

    short = "short"
    detailed = "detailed"
    by_topic = "by_topic"
    bullet_points = "bullet_points"


# OpenAPI / service parameter alias — same enum, not a second type.
SummaryStyle = SummaryType


class SummaryStatus(enum.StrEnum):
    """Async generation lifecycle for summaries (FR6 Part 2)."""

    processing = "processing"
    completed = "completed"
    failed = "failed"


class ExtractionStatus(enum.StrEnum):
    """Async generation lifecycle for extractions (FR7 Part 5) — same as Summary."""

    processing = "processing"
    completed = "completed"
    failed = "failed"


class ComparisonStatus(enum.StrEnum):
    """Async generation lifecycle for comparisons (FR8) — same as Summary/Extraction."""

    processing = "processing"
    completed = "completed"
    failed = "failed"


class ExtractionType(enum.StrEnum):
    """Aligned with OpenAPI Extraction.extraction_type."""

    table = "table"
    figures = "figures"
    entities = "entities"
    timeline = "timeline"


class ExtractionOutputFormat(enum.StrEnum):
    json = "json"
    table = "table"


# OpenAPI / task alias (same enum as ExtractionOutputFormat).
OutputFormat = ExtractionOutputFormat


class EntityExtractionMode(enum.StrEnum):
    """FR7 entity path selector — reuse graph entities vs dedicated LLM fallback."""

    REUSE_EXISTING_ENTITIES = "reuse"
    LLM_ENTITY_EXTRACTION = "llm"


class ReportFormat(enum.StrEnum):
    pdf = "pdf"
    docx = "docx"
    markdown = "markdown"


class ReportStatus(enum.StrEnum):
    """From OpenAPI Report.status (not listed in ERD; required by API contract)."""

    pending = "pending"
    ready = "ready"
    failed = "failed"


class ReportSourceType(enum.StrEnum):
    """Aligned with OpenAPI ReportItemInput.source_type (chat_session)."""

    summary = "summary"
    extraction = "extraction"
    comparison = "comparison"
    chat_session = "chat_session"
