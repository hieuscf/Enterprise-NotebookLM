# =============================================================================
# File: parent_resolver.py
# Module/Service: Pipeline Worker — Hierarchical Chunking ([AI])
# Layer: Service
# Purpose: Resolve planned parent_temp_id values to persisted chunk UUIDs.
# Responsibilities:
#   - Map temp IDs after sequential DB insert
# Dependencies:
#   - app.ai.hierarchical_chunking.types
# Public Exports:
#   - resolve_parent_chunk_id
# Database/Table: document_chunks.parent_chunk_id
# Related Modules: app.services.hierarchical_chunking
# Important Notes: Planned order must list parents before dependents.
# =============================================================================

from __future__ import annotations

from uuid import UUID

from app.ai.hierarchical_chunking.types import PlannedChunk


def resolve_parent_chunk_id(
    planned: PlannedChunk,
    temp_to_db: dict[str, UUID],
) -> UUID | None:
    """Look up the persisted parent UUID for one planned chunk."""
    if not planned.parent_temp_id:
        return None
    return temp_to_db.get(planned.parent_temp_id)
