# =============================================================================
# File: __init__.py
# Module/Service: Query Router — Interfaces (FR11)
# Layer: Adapter
# Purpose: Export Retriever / MetadataRepository protocols.
# Responsibilities:
#   - Re-export Protocol types for handlers and DI
# Dependencies:
#   - interfaces.retriever, interfaces.metadata_repository
# Public Exports:
#   - Retriever, RetrievedChunk, MetadataRepository, MetadataDocumentInfo
# Database/Table: N/A
# Related Modules: handlers.*
# Important Notes: N/A
# =============================================================================

from app.services.query_router.interfaces.metadata_repository import (
    MetadataDocumentInfo,
    MetadataRepository,
)
from app.services.query_router.interfaces.query_log_repository import QueryLogRepository
from app.services.query_router.interfaces.retriever import RetrievedChunk, Retriever

__all__ = [
    "MetadataDocumentInfo",
    "MetadataRepository",
    "QueryLogRepository",
    "RetrievedChunk",
    "Retriever",
]
