# =============================================================================
# File: heuristics.py
# Module/Service: Event Policy Engine (FR14)
# Layer: Service
# Purpose: Pure heuristic predicates for trigger_reason classification (0 LLM).
# Responsibilities:
#   - is_structured_query / is_multi_hop_query / is_ambiguous_query
# Dependencies:
#   - normalize_query, MetadataPatternRegistry, RerankedItem, EventPolicyConfig
# Public Exports:
#   - EventPolicyConfig, build_event_policy_config,
#     is_structured_query, is_multi_hop_query, is_ambiguous_query
# Database/Table: N/A
# Related Modules: event_policy_engine, metadata_patterns, router_rules
# Important Notes: No Neo4j / embedding / LLM. Reuse MetadataPatternRegistry.
# =============================================================================

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings
from app.models.enums import RouteType
from app.services.query_router.metadata_patterns import (
    MetadataPatternRegistry,
)
from app.services.query_router.normalizer import normalize_query
from app.services.retrieval.confidence_engine import RerankedItem

# Pronouns / underspecified ask patterns (VI + EN) — ambiguous rewrite candidates.
_AMBIGUOUS_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in (
        r"\b(cái\s+này|cái\s+đó|điều\s+này|việc\s+này)\b",
        r"\b(nó|chúng|this|that|it|these|those)\b",
        r"\b(giải\s+thích\s+thêm|cho\s+tôi\s+biết|tell\s+me\s+more|"
        r"explain\s+(this|more)|what\s+about\s+(this|that))\b",
        r"^(là\s+gì|what\s+is\s+(this|that|it))\b",
        r"\b(how\s+does\s+it\s+work|nó\s+hoạt\s+động)\b",
    )
)

# Relation / comparison markers → multi-hop / graph.
_MULTI_HOP_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in (
        r"\b(ảnh\s+hưởng|tác\s+động|quan\s+hệ|liên\s+quan|so\s+sánh|"
        r"khác\s+gì|khác\s+nhau|giữa)\b",
        r"\b(affect|affects|impact|relationship|related\s+to|compare|"
        r"comparison|versus|vs\.?|between|difference|differ)\b",
        r"\b(how\s+.+\s+affect|ảnh\s+hưởng\s+.+\s+đến)\b",
    )
)

# Lightweight "two entities" cue: "A and/và/với/vs B" style.
_ENTITY_PAIR_RE = re.compile(
    r"\b([\w][\w\-.]{1,40})\s+(?:and|và|với|vs\.?|versus|v\.s\.?)\s+([\w][\w\-.]{1,40})\b",
    re.IGNORECASE | re.UNICODE,
)

_TOKEN_RE = re.compile(r"\S+", re.UNICODE)


class EventPolicyConfig(BaseModel):
    """Tunable heuristic thresholds (env-backed via Settings)."""

    model_config = ConfigDict(frozen=True)

    ambiguous_max_tokens: int = Field(ge=1)
    ambiguous_score_spread_max: float = Field(ge=0.0, le=1.0)
    multi_hop_min_doc_diversity: int = Field(ge=1)
    multi_hop_top_k: int = Field(ge=1)


def build_event_policy_config(settings: Settings) -> EventPolicyConfig:
    """Map ``Settings`` → ``EventPolicyConfig``."""
    return EventPolicyConfig(
        ambiguous_max_tokens=max(1, int(settings.event_policy_ambiguous_max_tokens)),
        ambiguous_score_spread_max=float(settings.event_policy_ambiguous_score_spread_max),
        multi_hop_min_doc_diversity=max(
            1, int(settings.event_policy_multi_hop_min_doc_diversity)
        ),
        multi_hop_top_k=max(1, int(settings.event_policy_multi_hop_top_k)),
    )


def is_structured_query(
    query_text: str,
    route_type_hint: str,
    *,
    pattern_registry: MetadataPatternRegistry | None = None,
) -> bool:
    """True when query looks like Metadata/SQL but was routed as complex.

    Reuses ``MetadataPatternRegistry`` (same phrases as Query Classifier).
    """
    hint = (route_type_hint or "").strip().lower()
    if hint and hint != RouteType.complex.value:
        return False

    registry = pattern_registry or MetadataPatternRegistry()
    normalized = normalize_query(query_text)
    match = registry.match(normalized)
    return bool(match.matched)


def is_multi_hop_query(
    query_text: str,
    reranked_results: Sequence[RerankedItem],
    *,
    config: EventPolicyConfig,
) -> bool:
    """True when query needs multi-entity / relation expansion (Graph Agent)."""
    normalized = normalize_query(query_text)
    if not normalized:
        return False

    for pattern in _MULTI_HOP_PATTERNS:
        if pattern.search(normalized):
            return True

    if _ENTITY_PAIR_RE.search(normalized):
        return True

    # Top rerank spans multiple documents → likely multi-hop context.
    if _document_diversity(reranked_results, top_k=config.multi_hop_top_k) >= (
        config.multi_hop_min_doc_diversity
    ):
        # Require at least a weak relational cue or multiple seed entities.
        seed_entities = {
            item.entity_id for item in reranked_results[: config.multi_hop_top_k] if item.entity_id
        }
        if len(seed_entities) >= 2:
            return True

    return False


def is_ambiguous_query(
    query_text: str,
    reranked_results: Sequence[RerankedItem],
    *,
    config: EventPolicyConfig,
) -> bool:
    """True when query is short / pronoun-heavy / rerank does not converge."""
    normalized = normalize_query(query_text)
    tokens = _TOKEN_RE.findall(normalized)

    if len(tokens) <= config.ambiguous_max_tokens:
        return True

    for pattern in _AMBIGUOUS_PATTERNS:
        if pattern.search(normalized):
            return True

    spread = _score_spread(reranked_results)
    if spread is not None and spread <= config.ambiguous_score_spread_max:
        # Near-tie across topics/docs reinforces ambiguity.
        if _document_diversity(reranked_results, top_k=config.multi_hop_top_k) >= 2:
            return True
        if len(reranked_results) >= 2:
            return True

    return False


def _score_spread(reranked_results: Sequence[RerankedItem]) -> float | None:
    if len(reranked_results) < 2:
        return None
    ordered = sorted(
        reranked_results,
        key=lambda item: (
            item.rank is None,
            item.rank if item.rank is not None else 10**9,
        ),
    )
    top = float(ordered[0].score if ordered[0].score is not None else 0.0)
    second = float(ordered[1].score if ordered[1].score is not None else 0.0)
    return top - second


def _document_diversity(reranked_results: Sequence[RerankedItem], *, top_k: int) -> int:
    docs: set[str] = set()
    for item in list(reranked_results)[: max(1, top_k)]:
        if item.document_id:
            docs.add(str(item.document_id))
    return len(docs)
