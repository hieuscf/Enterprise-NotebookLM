# =============================================================================
# File: classifier.py
# Module/Service: Query Router — Rule-based Classifier (FR11)
# Layer: Service
# Purpose: Metadata / Factoid / Complex classification without LLM.
# Responsibilities:
#   - Detect metadata via regex/keywords from RouterRules
#   - Detect factoid pattern + length; score gate uses retrieval top-1
# Dependencies:
#   - app.config.router_rules.RouterRules
# Public Exports:
#   - RuleBasedClassifier
# Database/Table: N/A
# Related Modules: app.services.query_router.router
# Important Notes: Does not call Hybrid Retrieval — router orchestrates that.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass

from app.config.router_rules import RouterRules
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MetadataMatch:
    matched: bool
    pattern: str | None = None


@dataclass(frozen=True, slots=True)
class FactoidPatternMatch:
    matched: bool
    pattern: str | None = None
    too_long: bool = False


class RuleBasedClassifier:
    """Rule-based query classifier (metadata / factoid patterns)."""

    def __init__(self, rules: RouterRules) -> None:
        self._rules = rules

    def match_metadata(self, normalized_query: str) -> MetadataMatch:
        """Return whether ``normalized_query`` matches metadata rules."""
        q = (normalized_query or "").strip()
        if not q:
            return MetadataMatch(matched=False)
        m = self._rules.metadata_regex.search(q)
        if m:
            return MetadataMatch(matched=True, pattern=m.group(0))
        return MetadataMatch(matched=False)

    def match_factoid_pattern(self, normalized_query: str) -> FactoidPatternMatch:
        """Return whether query looks like a short factoid question."""
        q = (normalized_query or "").strip()
        if not q:
            return FactoidPatternMatch(matched=False)
        too_long = len(q) > self._rules.maximum_factoid_length
        m = self._rules.factoid_regex.search(q)
        if m and not too_long:
            return FactoidPatternMatch(matched=True, pattern=m.group(0), too_long=False)
        if m and too_long:
            return FactoidPatternMatch(matched=False, pattern=m.group(0), too_long=True)
        return FactoidPatternMatch(matched=False, too_long=too_long)

    def is_factoid(
        self,
        normalized_query: str,
        *,
        top_score: float | None,
    ) -> tuple[bool, str]:
        """Decide factoid route given pattern match + retrieval top-1 score.

        Args:
            normalized_query: Normalized query text.
            top_score: Score of retrieval top-1 (None if no hit).

        Returns:
            ``(is_factoid, reason)``.
        """
        pattern = self.match_factoid_pattern(normalized_query)
        if pattern.too_long:
            return False, "factoid_pattern_but_query_too_long"
        if not pattern.matched:
            return False, "no_factoid_pattern"
        if top_score is None:
            return False, "factoid_pattern_but_no_retrieval_hit"
        min_score = max(
            self._rules.factoid_confidence_threshold,
            self._rules.minimum_factoid_score,
        )
        if top_score < min_score:
            return (
                False,
                f"factoid_score_below_threshold:{top_score:.4f}<{min_score:.4f}",
            )
        return True, f"factoid_pattern={pattern.pattern};score={top_score:.4f}"
