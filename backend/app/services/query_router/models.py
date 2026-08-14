# =============================================================================
# File: models.py
# Module/Service: Query Router — Query Classifier (FR11)
# Layer: Service
# Purpose: Internal result types for classification (not API schemas).
# Responsibilities:
#   - Carry route decision details (confidence, margin, matched pattern)
# Dependencies:
#   - app.models.enums.RouteType
# Public Exports:
#   - ClassificationResult, MetadataMatchResult
# Database/Table: N/A
# Related Modules: app.services.query_router.rule_classifier
# Important Notes: route_type is never cache_hit from the classifier.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import RouteType


@dataclass(frozen=True, slots=True)
class MetadataMatchResult:
    """Result of metadata pattern matching against a normalized query."""

    matched: bool
    rule_name: str | None = None
    pattern: str | None = None
    priority: int | None = None


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Detailed classification outcome for logging / debugging.

    Attributes:
        route_type: ``metadata`` | ``factoid`` | ``complex`` (never ``cache_hit``).
        reason: Human-readable decision rationale.
        confidence: Cosine similarity to winning centroid (embedding path), else 1.0.
        margin: Absolute gap between factoid and complex similarities.
        metadata_rule: Matched metadata rule name when applicable.
        section_rule: Matched section-extraction rule name when applicable.
    """

    route_type: RouteType
    reason: str
    confidence: float | None = None
    margin: float | None = None
    metadata_rule: str | None = None
    section_rule: str | None = None
