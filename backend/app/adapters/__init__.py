# =============================================================================
# File: __init__.py
# Module/Service: Adapters
# Layer: Adapter
# Purpose: Package marker for external system clients (MinIO, ES, Qdrant, Neo4j).
# Responsibilities:
#   - Group infrastructure adapters used by Document Ingestion / Pipeline Worker
# Dependencies:
#   - N/A
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.adapters.minio_storage, qdrant_store, elasticsearch_bm25, neo4j_graph
# Important Notes: Celery must not call Anthropic; LLM adapters live under backend-api only.
# =============================================================================
