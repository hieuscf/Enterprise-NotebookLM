# =============================================================================
# File: router_rules.py
# Module/Service: Query Router (FR11)
# Layer: Adapter
# Purpose: Centralized rule / threshold config for Query Router classification.
# Responsibilities:
#   - Expose RouterRules loaded from Settings (no hardcoding in router code)
#   - Hold metadata / factoid keyword & regex patterns (VI + EN)
# Dependencies:
#   - app.core.config.Settings
# Public Exports:
#   - RouterRules, get_router_rules, QDRANT_QUERY_CACHE_KIND
# Database/Table: N/A
# Related Modules: app.services.query_router.*
# Important Notes: 0 LLM. Patterns are rule-based only.
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import Settings, get_settings

# Qdrant payload.kind for semantic query_cache vectors (shared collection).
QDRANT_QUERY_CACHE_KIND = "query_cache"

# Default keyword lists — override only via Settings-backed RouterRules factory
# if Settings gains list fields later; keep literals here (not in router.py).
_DEFAULT_METADATA_KEYWORDS_VI: tuple[str, ...] = (
    "có bao nhiêu",
    "danh sách",
    "liệt kê",
    "thống kê",
    "tất cả",
    "tổng số",
    "bao nhiêu tài liệu",
    "số lượng",
)
_DEFAULT_METADATA_KEYWORDS_EN: tuple[str, ...] = (
    "how many",
    "list all",
    "list",
    "show all",
    "count",
    "statistics",
    "total number",
    "number of",
)
_DEFAULT_FACTOID_KEYWORDS_VI: tuple[str, ...] = (
    "là gì",
    "ai là",
    "là ai",
    "khi nào",
    "ở đâu",
    "bao giờ",
    "định nghĩa",
)
_DEFAULT_FACTOID_KEYWORDS_EN: tuple[str, ...] = (
    "what is",
    "what are",
    "who is",
    "who are",
    "where is",
    "where are",
    "when is",
    "when was",
    "when were",
    "define",
)


@dataclass(frozen=True, slots=True)
class RouterRules:
    """Immutable rule set consumed by Query Router cache + classifier."""

    similarity_threshold: float
    factoid_confidence_threshold: float
    minimum_factoid_score: float
    maximum_factoid_length: int
    factoid_top_k: int
    metadata_regex: re.Pattern[str]
    factoid_regex: re.Pattern[str]
    metadata_keywords: tuple[str, ...] = ()
    factoid_keywords: tuple[str, ...] = ()
    query_cache_kind: str = QDRANT_QUERY_CACHE_KIND


def _compile_keyword_regex(keywords: tuple[str, ...]) -> re.Pattern[str]:
    """Build a case-insensitive alternation regex from keyword phrases."""
    escaped = [re.escape(k.strip()) for k in keywords if k and k.strip()]
    if not escaped:
        return re.compile(r"(?!)")  # never matches
    # Longer phrases first to prefer multi-word matches.
    escaped.sort(key=len, reverse=True)
    return re.compile(rf"(?:{'|'.join(escaped)})", re.IGNORECASE | re.UNICODE)


def build_router_rules(settings: Settings) -> RouterRules:
    """Construct ``RouterRules`` from application ``Settings``.

    Args:
        settings: Loaded application settings.

    Returns:
        Frozen ``RouterRules`` instance.
    """
    metadata_kw = _DEFAULT_METADATA_KEYWORDS_VI + _DEFAULT_METADATA_KEYWORDS_EN
    factoid_kw = _DEFAULT_FACTOID_KEYWORDS_VI + _DEFAULT_FACTOID_KEYWORDS_EN
    return RouterRules(
        similarity_threshold=float(settings.query_cache_similarity_threshold),
        factoid_confidence_threshold=float(
            settings.query_router_factoid_confidence_threshold
        ),
        minimum_factoid_score=float(settings.query_router_minimum_factoid_score),
        maximum_factoid_length=int(settings.query_router_maximum_factoid_length),
        factoid_top_k=max(1, int(settings.query_router_factoid_top_k)),
        metadata_regex=_compile_keyword_regex(metadata_kw),
        factoid_regex=_compile_keyword_regex(factoid_kw),
        metadata_keywords=metadata_kw,
        factoid_keywords=factoid_kw,
        query_cache_kind=QDRANT_QUERY_CACHE_KIND,
    )


@lru_cache
def get_router_rules() -> RouterRules:
    """Cached default rules from ``get_settings()``."""
    return build_router_rules(get_settings())
