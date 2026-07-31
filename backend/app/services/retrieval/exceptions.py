# =============================================================================
# File: exceptions.py
# Module/Service: Search Service / Hybrid Retrieval
# Layer: Service
# Purpose: Retrieval-layer exceptions (FR3).
# Responsibilities:
#   - Signal total retrieval failure when all parallel sources fail
# Dependencies:
#   - N/A
# Public Exports:
#   - RetrievalUnavailableError
# Database/Table: N/A
# Related Modules: app.services.retrieval.hybrid_retrieval_service
# Important Notes: Raised only when Vector + BM25 + Graph all fail/timeout.
# =============================================================================

from __future__ import annotations


class RetrievalUnavailableError(Exception):
    """Raised when every Hybrid Retrieval source fails or times out."""

    def __init__(self, message: str = "All retrieval sources failed") -> None:
        super().__init__(message)
