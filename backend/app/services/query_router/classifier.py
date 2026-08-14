# =============================================================================
# File: classifier.py
# Module/Service: Query Router — Query Classifier (FR11)
# Layer: Service
# Purpose: QueryClassifier Protocol — stable interface for all implementations.
# Responsibilities:
#   - Define classify(query_text, workspace_id) -> RouteType contract
# Dependencies:
#   - app.models.enums.RouteType
# Public Exports:
#   - QueryClassifier, RuleBasedClassifier, build_rule_based_classifier
# Database/Table: N/A
# Related Modules: app.services.query_router.rule_classifier, router
# Important Notes:
#   - Implementations must NEVER return RouteType.cache_hit.
#   - Swap RuleBased / Embedding / TinyBERT without changing Query Router.
# =============================================================================

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.models.enums import RouteType


@runtime_checkable
class QueryClassifier(Protocol):
    """Intent classifier for Query Router (metadata / section_extraction / factoid / complex).

    Cache hits are a system state checked by the router — not by classifiers.
    """

    def classify(self, query_text: str, workspace_id: UUID) -> RouteType:
        """Classify ``query_text`` into a non-cache route type.

        Args:
            query_text: Raw user question.
            workspace_id: Tenant scope (reserved for future per-workspace rules).

        Returns:
            ``RouteType.metadata``, ``RouteType.section_extraction``,
            ``RouteType.factoid``, or ``RouteType.complex``.
            Must never return ``RouteType.cache_hit``.
        """
        ...


# Re-export implementation so existing imports keep working.
from app.services.query_router.rule_classifier import (  # noqa: E402
    RuleBasedClassifier,
    build_rule_based_classifier,
)

__all__ = [
    "QueryClassifier",
    "RuleBasedClassifier",
    "build_rule_based_classifier",
]
