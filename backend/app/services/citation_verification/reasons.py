# =============================================================================
# File: reasons.py
# Module/Service: Citation Verification Layer (FR5)
# Layer: Domain
# Purpose: Stable verification reason constants (no stack traces in API).
# Responsibilities:
#   - Enumerate accept / reject reasons for citation-level verification
# Dependencies:
#   - enum (stdlib)
# Public Exports:
#   - VerificationReason
# Database/Table: N/A
# Related Modules: citation_verification.results, citation_verification.service
# Important Notes:
#   - Deterministic verification. No LLM call.
#   - Must validate workspace/message/retrieval membership.
# =============================================================================

from __future__ import annotations

from enum import StrEnum


class VerificationReason(StrEnum):
    """Why a citation was accepted or rejected (log/metrics only)."""

    VALID = "VALID"
    CITATION_NOT_FOUND = "CITATION_NOT_FOUND"
    WRONG_MESSAGE = "WRONG_MESSAGE"
    WRONG_WORKSPACE = "WRONG_WORKSPACE"
    RETRIEVAL_NOT_FOUND = "RETRIEVAL_NOT_FOUND"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SNIPPET_NOT_IN_SOURCE = "SNIPPET_NOT_IN_SOURCE"
    EMPTY_SNIPPET = "EMPTY_SNIPPET"
    INVALID_RETRIEVAL_REFERENCE = "INVALID_RETRIEVAL_REFERENCE"
    DUPLICATE = "DUPLICATE"
