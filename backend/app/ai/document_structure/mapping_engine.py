# =============================================================================
# File: mapping_engine.py
# Module/Service: Clause Identity & Mapping (FR8 / TASK-CMP-03)
# Layer: Service
# Purpose: Map every numbered unit in document V1 to V2 from FULL structures.
# Responsibilities:
#   - Exact identity → title → parent/relative number → lexical → optional semantic
#   - One-to-one constraint, ambiguity margin, unmatched (not ADDED/REMOVED)
#   - Optional embed/rerank hooks; failures fall back to deterministic scores
# Dependencies:
#   - mapping_types, mapping_config, mapping_similarity, NormalizedDocumentStructure
# Public Exports:
#   - map_normalized_structures, score_pair, mappable_units
# Database/Table: N/A
# Related Modules: ClauseMappingEngine; TASK-CMP-04 consumes MappingResult
# Important Notes:
#   - 0 LLM. Does not use top-k RAG / user query / Elasticsearch BM25 search.
#   - Does not mutate original_title / original_text on NormalizedUnit.
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

from app.ai.document_structure.mapping_config import MappingConfig
from app.ai.document_structure.mapping_similarity import (
    cosine_similarity,
    last_number_part,
    lexical_similarity,
    title_similarity,
)
from app.ai.document_structure.mapping_types import (
    ClauseMapping,
    MappingCandidate,
    MappingResult,
    MappingSignals,
    MappingStatus,
    MappingType,
    clause_ref,
)
from app.ai.document_structure.normalization import (
    NormalizedDocumentStructure,
    NormalizedUnit,
)
from app.ai.document_structure.types import TYPE_LEVEL, StructuralUnitType

EmbedFn = Callable[[list[str]], list[list[float]]]
RerankFn = Callable[[str, str], float]


def mappable_units(structure: NormalizedDocumentStructure) -> list[NormalizedUnit]:
    """Numbered structural units only — the full clause set, not a retrieval slice."""
    return [
        unit
        for unit in structure.walk()
        if unit.type is not StructuralUnitType.DOCUMENT and unit.identity_key
    ]


def map_normalized_structures(
    source: NormalizedDocumentStructure,
    target: NormalizedDocumentStructure,
    *,
    config: MappingConfig | None = None,
    embed_fn: EmbedFn | None = None,
    rerank_fn: RerankFn | None = None,
) -> MappingResult:
    """Map every mappable unit in ``source`` against the full ``target`` tree."""
    started = time.perf_counter()
    cfg = config or MappingConfig()
    source_units = mappable_units(source)
    target_units = mappable_units(target)
    used_source: set[int] = set()
    used_target: set[int] = set()
    parent_pairs: dict[str, str] = {}
    rows: list[ClauseMapping] = []
    semantic_calls = 0
    reranker_calls = 0
    candidate_total = 0

    vectors = _safe_embed(source_units, target_units, embed_fn, cfg)
    if vectors is not None:
        semantic_calls = len(source_units) + len(target_units)

    levels = sorted({TYPE_LEVEL[u.type] for u in source_units + target_units})
    for level in levels:
        src_level = [u for u in source_units if TYPE_LEVEL[u.type] == level]
        tgt_level = [u for u in target_units if TYPE_LEVEL[u.type] == level]
        level_rows, cand_n, rerank_n = _map_level(
            src_level,
            tgt_level,
            used_source=used_source,
            used_target=used_target,
            parent_pairs=parent_pairs,
            config=cfg,
            vectors=vectors,
            rerank_fn=rerank_fn if cfg.enable_reranker else None,
            source_version_id=source.version_id,
            target_version_id=target.version_id,
        )
        rows.extend(level_rows)
        candidate_total += cand_n
        reranker_calls += rerank_n
        for row in level_rows:
            if row.accepted and row.source_unit and row.target_unit:
                if row.source_unit.identity_key and row.target_unit.identity_key:
                    parent_pairs[row.source_unit.identity_key] = (
                        row.target_unit.identity_key
                    )

    unmatched_targets = [
        _unmatched(
            source=None,
            target=unit,
            source_version_id=source.version_id,
            target_version_id=target.version_id,
        )
        for unit in target_units
        if id(unit) not in used_target
    ]

    duration_ms = int((time.perf_counter() - started) * 1000)
    metadata = _metadata(
        source_units,
        target_units,
        rows,
        unmatched_targets,
        duration_ms=duration_ms,
        candidate_total=candidate_total,
        semantic_calls=semantic_calls,
        reranker_calls=reranker_calls,
    )
    return MappingResult(
        source_document_id=source.document_id,
        target_document_id=target.document_id,
        source_version_id=source.version_id,
        target_version_id=target.version_id,
        mappings=rows,
        unmatched_targets=unmatched_targets,
        metadata=metadata,
    )


def score_pair(
    source: NormalizedUnit,
    target: NormalizedUnit,
    *,
    config: MappingConfig | None = None,
    parent_pairs: dict[str, str] | None = None,
    semantic: float | None = None,
    reranker: float | None = None,
) -> tuple[float, MappingSignals]:
    """Weighted evidence score. Original text is read, never written."""
    cfg = config or MappingConfig()
    parents = parent_pairs or {}
    number_match = bool(
        source.identity_key
        and source.identity_key == target.identity_key
    )
    type_match = source.type is target.type
    parent_match = _parent_match(source, target, parents)
    relative = (
        type_match
        and last_number_part(source.canonical_number)
        == last_number_part(target.canonical_number)
        and last_number_part(source.canonical_number) is not None
    )
    title = max(
        title_similarity(source.normalized_title, target.normalized_title),
        title_similarity(source.folded_title, target.folded_title),
        _alias_overlap(source, target),
    )
    lexical = max(
        lexical_similarity(source.normalized_body, target.normalized_body),
        lexical_similarity(source.folded_body, target.folded_body),
        lexical_similarity(source.normalized_title, target.normalized_title),
    )
    position = _position_score(source.order_index, target.order_index)
    score = (
        cfg.weight_number * (1.0 if number_match else 0.0)
        + cfg.weight_type * (1.0 if type_match else 0.0)
        + cfg.weight_parent * (1.0 if parent_match else 0.0)
        + cfg.weight_title * title
        + cfg.weight_lexical * lexical
        + cfg.weight_position * position
    )
    if semantic is not None:
        score += cfg.weight_semantic * semantic
    elif number_match:
        score += cfg.weight_semantic
    if reranker is not None:
        score = min(1.0, 0.85 * score + 0.15 * max(0.0, min(1.0, reranker)))
    if number_match and type_match:
        score = max(score, cfg.exact_min)
    if relative and parent_match and title >= 0.8:
        score = max(score, cfg.high_min)
    if title >= 0.99 and type_match and lexical >= 0.45:
        score = max(score, cfg.high_min)
    score = max(0.0, min(1.0, score))
    method = _method_name(number_match, parent_match, relative, title, lexical, semantic)
    signals = MappingSignals(
        number_match=number_match,
        type_match=type_match,
        parent_match=parent_match,
        title_similarity=title,
        lexical_similarity=lexical,
        semantic_similarity=semantic,
        reranker_score=reranker,
        structural_position=position,
        relative_number_match=relative,
        method=method,
    )
    return score, signals


def _map_level(
    sources: Sequence[NormalizedUnit],
    targets: Sequence[NormalizedUnit],
    *,
    used_source: set[int],
    used_target: set[int],
    parent_pairs: dict[str, str],
    config: MappingConfig,
    vectors: dict[int, list[float]] | None,
    rerank_fn: RerankFn | None,
    source_version_id: UUID | None,
    target_version_id: UUID | None,
) -> tuple[list[ClauseMapping], int, int]:
    rows: list[ClauseMapping] = []
    candidate_total = 0
    reranker_calls = 0

    open_sources = [u for u in sources if id(u) not in used_source]
    open_targets = [u for u in targets if id(u) not in used_target]

    # Phase A — exact identity_key (deterministic, 0 similarity).
    for source in list(open_sources):
        hits = [
            t
            for t in open_targets
            if t.identity_key == source.identity_key and id(t) not in used_target
        ]
        if len(hits) == 1:
            row = _accept(
                source,
                hits[0],
                parent_pairs=parent_pairs,
                config=config,
                vectors=vectors,
                source_version_id=source_version_id,
                target_version_id=target_version_id,
            )
            rows.append(row)
            used_source.add(id(source))
            used_target.add(id(hits[0]))
        elif len(hits) > 1:
            scored = _score_candidates(
                source,
                hits,
                parent_pairs=parent_pairs,
                config=config,
                vectors=vectors,
                rerank_fn=rerank_fn,
            )
            candidate_total += len(scored)
            reranker_calls += _rerank_count(scored)
            row = _resolve_scored(
                source,
                scored,
                config=config,
                used_target=used_target,
                source_version_id=source_version_id,
                target_version_id=target_version_id,
            )
            rows.append(row)
            used_source.add(id(source))
            if row.accepted and row.target_unit is not None:
                used_target.add(id(row.target_unit))

    open_sources = [u for u in sources if id(u) not in used_source]
    open_targets = [u for u in targets if id(u) not in used_target]

    # Phases B–F — pruned candidates, then one-to-one / ambiguous.
    for source in open_sources:
        pool = _candidate_pool(source, open_targets, used_target, parent_pairs, config)
        candidate_total += len(pool)
        if not pool:
            rows.append(
                _unmatched(
                    source=source,
                    target=None,
                    source_version_id=source_version_id,
                    target_version_id=target_version_id,
                )
            )
            used_source.add(id(source))
            continue
        scored = _score_candidates(
            source,
            pool,
            parent_pairs=parent_pairs,
            config=config,
            vectors=vectors,
            rerank_fn=rerank_fn,
        )
        reranker_calls += _rerank_count(scored)
        row = _resolve_scored(
            source,
            scored,
            config=config,
            used_target=used_target,
            source_version_id=source_version_id,
            target_version_id=target_version_id,
        )
        rows.append(row)
        used_source.add(id(source))
        if row.accepted and row.target_unit is not None:
            used_target.add(id(row.target_unit))
            open_targets = [u for u in open_targets if id(u) not in used_target]

    return rows, candidate_total, reranker_calls


def _candidate_pool(
    source: NormalizedUnit,
    targets: Sequence[NormalizedUnit],
    used_target: set[int],
    parent_pairs: dict[str, str],
    config: MappingConfig,
) -> list[NormalizedUnit]:
    """Prune to same type + title/parent/number/window — never full Cartesian."""
    same_type = [
        t
        for t in targets
        if id(t) not in used_target and t.type is source.type
    ]
    if not same_type:
        return []
    selected: list[NormalizedUnit] = []
    seen: set[int] = set()

    def add(unit: NormalizedUnit) -> None:
        if id(unit) not in seen:
            seen.add(id(unit))
            selected.append(unit)

    for target in same_type:
        if source.folded_title and source.folded_title == target.folded_title:
            add(target)
        if source.normalized_title and source.normalized_title == target.normalized_title:
            add(target)
        if _alias_overlap(source, target) >= 0.99:
            add(target)
        if _parent_match(source, target, parent_pairs) and last_number_part(
            source.canonical_number
        ) == last_number_part(target.canonical_number):
            add(target)
        if (
            source.order_index is not None
            and target.order_index is not None
            and abs(source.order_index - target.order_index) <= config.order_window
        ):
            add(target)

    if len(selected) < 2 and len(same_type) <= config.max_same_type_comparisons:
        for target in same_type:
            add(target)
    elif not selected:
        ranked = sorted(
            same_type,
            key=lambda t: title_similarity(
                source.normalized_title or source.folded_title,
                t.normalized_title or t.folded_title,
            ),
            reverse=True,
        )
        for target in ranked[: config.max_candidates_per_source]:
            add(target)
    return selected[: config.max_candidates_per_source]


def _score_candidates(
    source: NormalizedUnit,
    targets: Sequence[NormalizedUnit],
    *,
    parent_pairs: dict[str, str],
    config: MappingConfig,
    vectors: dict[int, list[float]] | None,
    rerank_fn: RerankFn | None,
) -> list[tuple[NormalizedUnit, float, MappingSignals]]:
    scored: list[tuple[NormalizedUnit, float, MappingSignals]] = []
    for target in targets:
        semantic = None
        if vectors and id(source) in vectors and id(target) in vectors:
            semantic = cosine_similarity(vectors[id(source)], vectors[id(target)])
        rerank = None
        if rerank_fn is not None:
            try:
                rerank = float(
                    rerank_fn(
                        source.normalized_body or source.normalized_title,
                        target.normalized_body or target.normalized_title,
                    )
                )
            except Exception:  # noqa: BLE001 — optional layer must not fail mapping
                rerank = None
        score, signals = score_pair(
            source,
            target,
            config=config,
            parent_pairs=parent_pairs,
            semantic=semantic,
            reranker=rerank,
        )
        scored.append((target, score, signals))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def _resolve_scored(
    source: NormalizedUnit,
    scored: list[tuple[NormalizedUnit, float, MappingSignals]],
    *,
    config: MappingConfig,
    used_target: set[int],
    source_version_id: UUID | None,
    target_version_id: UUID | None,
) -> ClauseMapping:
    available = [item for item in scored if id(item[0]) not in used_target]
    if not available:
        return _unmatched(
            source=source,
            target=None,
            source_version_id=source_version_id,
            target_version_id=target_version_id,
        )
    best_target, best_score, best_signals = available[0]
    second_score = available[1][1] if len(available) > 1 else None
    margin = None if second_score is None else best_score - second_score
    signals = MappingSignals(
        number_match=best_signals.number_match,
        type_match=best_signals.type_match,
        parent_match=best_signals.parent_match,
        title_similarity=best_signals.title_similarity,
        lexical_similarity=best_signals.lexical_similarity,
        semantic_similarity=best_signals.semantic_similarity,
        reranker_score=best_signals.reranker_score,
        structural_position=best_signals.structural_position,
        candidate_margin=margin,
        relative_number_match=best_signals.relative_number_match,
        method=best_signals.method,
    )
    level_name = config.classify(
        best_score,
        number_match=signals.number_match,
        type_match=signals.type_match,
    )
    level = MappingStatus(level_name)
    candidates = [
        MappingCandidate(
            target_source_id=item[0].source_id,
            target_identity_key=item[0].identity_key,
            confidence=item[1],
            signals=item[2],
        )
        for item in available[: config.max_candidates_per_source]
    ]
    strong_seconds = [
        item
        for item in available[1:]
        if item[1] >= config.medium_min
    ]
    if (
        level in {MappingStatus.HIGH_CONFIDENCE, MappingStatus.MEDIUM_CONFIDENCE, MappingStatus.EXACT}
        and strong_seconds
        and margin is not None
        and margin < config.ambiguous_margin
    ):
        mapping_type = (
            MappingType.ONE_TO_MANY_CANDIDATE
            if len(strong_seconds) >= 1
            else MappingType.TITLE
        )
        return ClauseMapping(
            source_unit=source,
            target_unit=None,
            mapping_type=mapping_type,
            confidence=best_score,
            confidence_level=MappingStatus.AMBIGUOUS,
            signals=signals,
            source_ref=clause_ref(source, version_id=source_version_id),
            target_ref=None,
            candidates=candidates,
        )
    if level is MappingStatus.UNMATCHED:
        return _unmatched(
            source=source,
            target=None,
            source_version_id=source_version_id,
            target_version_id=target_version_id,
            candidates=candidates,
            signals=signals,
            confidence=best_score,
        )
    return ClauseMapping(
        source_unit=source,
        target_unit=best_target,
        mapping_type=_mapping_type(signals, level),
        confidence=best_score,
        confidence_level=level,
        signals=signals,
        source_ref=clause_ref(source, version_id=source_version_id),
        target_ref=clause_ref(best_target, version_id=target_version_id),
        candidates=candidates,
    )


def _accept(
    source: NormalizedUnit,
    target: NormalizedUnit,
    *,
    parent_pairs: dict[str, str],
    config: MappingConfig,
    vectors: dict[int, list[float]] | None,
    source_version_id: UUID | None,
    target_version_id: UUID | None,
) -> ClauseMapping:
    semantic = None
    if vectors and id(source) in vectors and id(target) in vectors:
        semantic = cosine_similarity(vectors[id(source)], vectors[id(target)])
    score, signals = score_pair(
        source,
        target,
        config=config,
        parent_pairs=parent_pairs,
        semantic=semantic,
    )
    return ClauseMapping(
        source_unit=source,
        target_unit=target,
        mapping_type=MappingType.EXACT,
        confidence=max(score, config.exact_min),
        confidence_level=MappingStatus.EXACT,
        signals=signals,
        source_ref=clause_ref(source, version_id=source_version_id),
        target_ref=clause_ref(target, version_id=target_version_id),
        candidates=[
            MappingCandidate(
                target_source_id=target.source_id,
                target_identity_key=target.identity_key,
                confidence=max(score, config.exact_min),
                signals=signals,
            )
        ],
    )


def _unmatched(
    *,
    source: NormalizedUnit | None,
    target: NormalizedUnit | None,
    source_version_id: UUID | None,
    target_version_id: UUID | None,
    candidates: list[MappingCandidate] | None = None,
    signals: MappingSignals | None = None,
    confidence: float = 0.0,
) -> ClauseMapping:
    empty = signals or MappingSignals(
        number_match=False,
        type_match=False,
        parent_match=False,
        title_similarity=0.0,
        lexical_similarity=0.0,
        method="unmatched",
    )
    return ClauseMapping(
        source_unit=source,
        target_unit=target,
        mapping_type=MappingType.ONE_TO_ONE,
        confidence=confidence,
        confidence_level=MappingStatus.UNMATCHED,
        signals=empty,
        source_ref=(
            clause_ref(source, version_id=source_version_id) if source else None
        ),
        target_ref=(
            clause_ref(target, version_id=target_version_id) if target else None
        ),
        candidates=list(candidates or []),
    )


def _parent_match(
    source: NormalizedUnit,
    target: NormalizedUnit,
    parent_pairs: dict[str, str],
) -> bool:
    if source.parent_identity_key and source.parent_identity_key == target.parent_identity_key:
        return True
    if (
        source.parent_identity_key
        and target.parent_identity_key
        and parent_pairs.get(source.parent_identity_key) == target.parent_identity_key
    ):
        return True
    return False


def _alias_overlap(source: NormalizedUnit, target: NormalizedUnit) -> float:
    left = set(source.aliases)
    right = set(target.aliases)
    if not left or not right:
        return 0.0
    if left & right:
        return 1.0
    return 0.0


def _position_score(left: int, right: int) -> float:
    gap = abs(left - right)
    return max(0.0, 1.0 - gap / 12.0)


def _method_name(
    number_match: bool,
    parent_match: bool,
    relative: bool,
    title: float,
    lexical: float,
    semantic: float | None,
) -> str:
    if number_match:
        return "exact_identity"
    if parent_match and relative:
        return "structural"
    if title >= 0.99:
        return "title"
    if semantic is not None and semantic >= 0.8 and semantic >= lexical:
        return "semantic"
    if lexical >= 0.5:
        return "lexical"
    return "mixed"


def _mapping_type(signals: MappingSignals, level: MappingStatus) -> MappingType:
    if level is MappingStatus.EXACT or signals.method == "exact_identity":
        return MappingType.EXACT
    if signals.method == "structural":
        return MappingType.STRUCTURAL
    if signals.method == "title":
        return MappingType.TITLE
    if signals.method == "semantic":
        return MappingType.SEMANTIC
    if signals.method == "lexical":
        return MappingType.LEXICAL
    return MappingType.ONE_TO_ONE


def _safe_embed(
    source_units: Sequence[NormalizedUnit],
    target_units: Sequence[NormalizedUnit],
    embed_fn: EmbedFn | None,
    config: MappingConfig,
) -> dict[int, list[float]] | None:
    if embed_fn is None or not config.enable_semantic:
        return None
    units = list(source_units) + list(target_units)
    texts = [
        (unit.normalized_body or unit.normalized_title or unit.identity_key or "")
        for unit in units
    ]
    try:
        vectors = embed_fn(texts)
    except Exception:  # noqa: BLE001 — semantic layer is optional
        return None
    if len(vectors) != len(units):
        return None
    return {id(unit): vector for unit, vector in zip(units, vectors, strict=True)}


def _rerank_count(scored: Sequence[tuple[Any, ...]]) -> int:
    return sum(1 for item in scored if item[2].reranker_score is not None)


def _metadata(
    source_units: Sequence[NormalizedUnit],
    target_units: Sequence[NormalizedUnit],
    rows: Sequence[ClauseMapping],
    unmatched_targets: Sequence[ClauseMapping],
    *,
    duration_ms: int,
    candidate_total: int,
    semantic_calls: int,
    reranker_calls: int,
) -> dict[str, Any]:
    counts = {status.value: 0 for status in MappingStatus}
    for row in rows:
        counts[row.confidence_level.value] += 1
    accepted = sum(1 for row in rows if row.accepted)
    return {
        "source_clause_count": len(source_units),
        "target_clause_count": len(target_units),
        "exact_mappings": counts[MappingStatus.EXACT.value],
        "high_confidence_mappings": counts[MappingStatus.HIGH_CONFIDENCE.value],
        "medium_confidence_mappings": counts[MappingStatus.MEDIUM_CONFIDENCE.value],
        "low_confidence_mappings": counts[MappingStatus.LOW_CONFIDENCE.value],
        "ambiguous_mappings": counts[MappingStatus.AMBIGUOUS.value],
        "unmatched_source": counts[MappingStatus.UNMATCHED.value],
        "unmatched_target": len(unmatched_targets),
        "accepted_mappings": accepted,
        "average_candidates_per_clause": (
            round(candidate_total / max(1, len(source_units)), 3)
        ),
        "semantic_matching_count": semantic_calls,
        "reranker_invocation_count": reranker_calls,
        "mapping_latency_ms": duration_ms,
        "mapping_llm_calls": 0,
    }
