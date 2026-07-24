# =============================================================================
# File: __init__.py
# Module/Service: Models
# Layer: Schema
# Purpose: Export all SQLAlchemy ORM models for Alembic metadata discovery.
# Responsibilities:
#   - Import every model so Base.metadata contains the full schema v2
# Dependencies:
#   - All app.models.* modules
# Public Exports:
#   - All ORM model classes (27 tables)
# Database/Table: Full schema v2
# Related Modules: alembic/env.py, database-design-enterprise-notebooklm.md
# Important Notes: Import order does not affect FK resolution (string FKs).
# =============================================================================

from app.models.artifacts import (
    Comparison,
    ComparisonDocument,
    Extraction,
    Report,
    ReportItem,
    Summary,
)
from app.models.chat import ChatMessage, ChatSession, MessageGeneration
from app.models.documents import Document, DocumentVersion
from app.models.identity import Role, User, Workspace, WorkspaceMember
from app.models.knowledge import (
    DocumentChunk,
    Embedding,
    Entity,
    EntityRelation,
    Topic,
    TopicChunk,
)
from app.models.pipeline import PipelineRun, PipelineStageLog
from app.models.query import QueryCache, QueryLog, SearchHistory
from app.models.retrieval import Citation, Retrieval

__all__ = [
    "User",
    "Workspace",
    "Role",
    "WorkspaceMember",
    "Document",
    "DocumentVersion",
    "PipelineRun",
    "PipelineStageLog",
    "Embedding",
    "DocumentChunk",
    "Entity",
    "EntityRelation",
    "Topic",
    "TopicChunk",
    "QueryCache",
    "ChatSession",
    "ChatMessage",
    "MessageGeneration",
    "Retrieval",
    "Citation",
    "SearchHistory",
    "QueryLog",
    "Summary",
    "Extraction",
    "Comparison",
    "ComparisonDocument",
    "Report",
    "ReportItem",
]
