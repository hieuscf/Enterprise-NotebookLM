# =============================================================================
# File: semantic_engine.py
# Module/Service: Semantic Clause Matching (FR8 / TASK-CMP-05)
# Layer: Service
# Purpose: Second-pass matching for unmatched / low-confidence CMP-03 rows.
# Responsibilities:
#   - Embed only leftover clauses; top-k cosine candidates; multi-signal score
#   - Never override EXACT / HIGH / MEDIUM accepted mappings
#   - Margin + structural gates; one-to-one; fallback if embed/rerank fails
# Dependencies:
#   - mapping_engine.score_pair, mapping_types, semantic_config, semantic_text
#   - HashingNgramEmbeddingProvider (default local embed; no LLM)
# Public Exports:
#   - refine_mapping_semantically, combined_semantic_score, types_compatible
# Database/Table: N/A
# Related Modules: ClauseSemanticMatcher; CMP-04 consumes refined MappingResult
# Important Notes:
#   - Semantic similarity is evidence, not identity.
#   - Does not use Qdrant chunk index / user-query RAG / Elasticsearch BM25.
#   - 0 LLM. Original text is never mutated.
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from app.ai.document_structure.mapping_engine import score_pair
from app.ai.document_structure.mapping_similarity import cosine_similarity, last_number_part
from app.ai.document_structure.mapping_types import (
    ClauseMapping,
    MappingCandidate,
    MappingResult,
    MappingSignals,
    MappingStatus,
    MappingType,
    clause_ref,
)
from app.ai.document_structure.normalization import NormalizedUnit
from app.ai.document_structure.semantic_config import SemanticMatchConfig
from app.ai.document_structure.semantic_text import EmbeddingCache, embedding_text
from app.ai.document_structure.types import TYPE_LEVEL, StructuralUnitType
from app.services.query_router.embedding_provider import HashingNgramEmbeddingProvider

EmbedFn = Callable[[list[str]], list[list[float]]]
RerankFn = Callable[[str, str], float]

_ACCEPTED = frozenset(
    {
        MappingStatus.EXACT,
        MappingStatus.HIGH_CONFIDENCE,
        MappingStatus.MEDIUM_CONFIDENCE,
    }
)
_REVIEW = frozenset(
    {
        MappingStatus.UNMATCHED,
        MappingStatus.LOW_CONFIDENCE,
        MappingStatus.AMBIGUOUS,
    }
)
_NEAR_TYPES = frozenset(
    {
        (StructuralUnitType.CLAUSE, StructuralUnitType.SUB_CLAUSE),
        (StructuralUnitType.SUB_CLAUSE, StructuralUnitType.CLAUSE),
        (StructuralUnitType.SUB_CLAUSE, StructuralUnitType.ITEM),
        (StructuralUnitType.ITEM, StructuralUnitType.SUB_CLAUSE),
    }
)

_DEFAULT_NGRAM = HashingNgramEmbeddingProvider(dimension=256)


def default_semantic_embed(texts: list[str]) -> list[list[float]]:
    """Local hashing-ngram vectors — overlapping tokens, no network, 0 LLM."""
    if not texts:
        return []
    matrix = _DEFAULT_NGRAM.embed(texts)
    return [row.tolist() for row in matrix]


def types_compatible(source: NormalizedUnit, target: NormalizedUnit) -> bool:
    """ARTICLE must not match APPENDIX (etc.) just because cosine is high."""
    if source.type is target.type:
        return True
    return (source.type, target.type) in _NEAR_TYPES


def sibling_number_mismatch(
    source: NormalizedUnit,
    target: NormalizedUnit,
    *,
    parent_pairs: dict[str, str],
) -> bool:
    """Same mapped parent, different last number — likely distinct siblings."""
    if source.type not in {
        StructuralUnitType.CLAUSE,
        StructuralUnitType.SUB_CLAUSE,
        StructuralUnitType.ITEM,
    }:
        return False
    if source.type is not target.type:
        return False
    src_last = last_number_part(source.canonical_number)
    tgt_last = last_number_part(target.canonical_number)
    if not src_last or not tgt_last or src_last == tgt_last:
        return False
    if source.parent_identity_key and source.parent_identity_key == target.parent_identity_key:
        return True
    mapped = parent_pairs.get(source.parent_identity_key or "")
    return bool(mapped and mapped == target.parent_identity_key)


def combined_semantic_score(
    signals: MappingSignals,
    *,
    config: SemanticMatchConfig,
    sibling_mismatch: bool,
) -> float:
    """Weighted multi-signal score with negative structural evidence."""
    semantic = signals.semantic_similarity if signals.semantic_similarity is not None else 0.0
    rerank = signals.reranker_score
    score = (
        config.weight_structural * (1.0 if signals.type_match else 0.0)
        + config.weight_title * signals.title_similarity
        + config.weight_lexical * signals.lexical_similarity
        + config.weight_semantic * semantic
        + config.weight_parent * (1.0 if signals.parent_match else 0.0)
        + config.weight_position * signals.structural_position
    )
    if rerank is not None:
        score += config.weight_reranker * max(0.0, min(1.0, rerank))
    else:
        score += config.weight_reranker * semantic
    if signals.relative_number_match:
        score += config.relative_number_bonus
    if sibling_mismatch:
        score -= config.sibling_mismatch_penalty
    if not signals.type_match:
        score -= config.incompatible_penalty
    return max(0.0, min(1.0, score))


def can_accept_semantic(
    score: float,
    signals: MappingSignals,
    *,
    margin: float | None,
    config: SemanticMatchConfig,
    sibling_mismatch: bool,
) -> bool:
    """Precision gates — cosine alone never accepts a mapping."""
    if config.require_type_match and not signals.type_match:
        return False
    if not types_compatible_from_signals(signals):
        return False
    if score < config.low_min:
        return False
    if margin is not None and margin < config.min_margin:
        return False
    semantic = signals.semantic_similarity if signals.semantic_similarity is not None else 0.0
    if (
        signals.title_similarity >= 0.9
        and signals.lexical_similarity < config.title_only_lexical_max
        and semantic < config.semantic_strong
    ):
        return False
    if sibling_mismatch and signals.title_similarity < 0.8 and signals.lexical_similarity < 0.85:
        return False
    # Reword / renumber: strong cosine is evidence, not identity — still need
    # type + (title or relative number or mapped parent) + some lexical overlap.
    if (
        semantic >= config.semantic_strong
        and signals.lexical_similarity >= config.reword_lexical_min
        and not sibling_mismatch
        and (
            signals.title_similarity >= 0.55
            or signals.relative_number_match
            or signals.parent_match
        )
    ):
        return True
    if score < config.accept_min:
        return False
    if signals.relative_number_match and (
        signals.parent_match or signals.title_similarity >= 0.70
    ):
        return True
    if signals.title_similarity >= 0.75 and signals.lexical_similarity >= config.lexical_floor:
        return True
    if signals.lexical_similarity >= 0.55 and signals.parent_match:
        return True
    return score >= config.high_min


def types_compatible_from_signals(signals: MappingSignals) -> bool:
    return signals.type_match or signals.method == "near_type"


def refine_mapping_semantically(
    mapping: MappingResult,
    *,
    config: SemanticMatchConfig | None = None,
    embed_fn: EmbedFn | None = None,
    rerank_fn: RerankFn | None = None,
    cache: EmbeddingCache | None = None,
) -> MappingResult:
    """Add semantic mappings for leftover clauses. Accepted CMP-03 rows stay."""
    started = time.perf_counter()
    cfg = config or SemanticMatchConfig()
    embed = embed_fn or default_semantic_embed
    store = cache or EmbeddingCache(model_name=cfg.model_name, model_version=cfg.model_version)
    if not store.compatible(cfg.model_name, cfg.model_version):
        store = EmbeddingCache(model_name=cfg.model_name, model_version=cfg.model_version)

    accepted = [row for row in mapping.mappings if row.confidence_level in _ACCEPTED]
    review = [row for row in mapping.mappings if row.confidence_level in _REVIEW]
    locked_targets = {
        id(row.target_unit) for row in accepted if row.target_unit is not None
    }
    parent_pairs = {
        row.source_unit.identity_key: row.target_unit.identity_key
        for row in accepted
        if row.source_unit
        and row.target_unit
        and row.source_unit.identity_key
        and row.target_unit.identity_key
    }

    review_sources = [row.source_unit for row in review if row.source_unit is not None]
    open_targets = _open_targets(mapping, review, locked_targets)
    metadata = dict(mapping.metadata)
    semantic_meta = {
        "semantic_layer": "cmp-05",
        "semantic_model_name": cfg.model_name,
        "semantic_model_version": cfg.model_version,
        "semantic_clauses_reviewed": len(review_sources),
        "semantic_open_targets": len(open_targets),
        "semantic_candidate_requests": 0,
        "semantic_candidates_generated": 0,
        "semantic_accepted": 0,
        "semantic_ambiguous": 0,
        "semantic_unmatched": 0,
        "semantic_reranker_calls": 0,
        "semantic_fallback_count": 0,
        "semantic_cache_hits": 0,
        "semantic_cache_misses": 0,
        "semantic_latency_ms": 0,
        "semantic_llm_calls": 0,
    }

    if not review_sources or not open_targets:
        semantic_meta["semantic_latency_ms"] = int((time.perf_counter() - started) * 1000)
        metadata.update(semantic_meta)
        return MappingResult(
            source_document_id=mapping.source_document_id,
            target_document_id=mapping.target_document_id,
            source_version_id=mapping.source_version_id,
            target_version_id=mapping.target_version_id,
            mappings=list(mapping.mappings),
            unmatched_targets=list(mapping.unmatched_targets),
            metadata=metadata,
        )

    vectors, fallback = _embed_units(
        review_sources + open_targets,
        embed_fn=embed,
        cache=store,
        config=cfg,
    )
    if fallback or vectors is None:
        semantic_meta["semantic_fallback_count"] = 1
        semantic_meta["semantic_cache_hits"] = store.hits
        semantic_meta["semantic_cache_misses"] = store.misses
        semantic_meta["semantic_latency_ms"] = int((time.perf_counter() - started) * 1000)
        metadata.update(semantic_meta)
        return MappingResult(
            source_document_id=mapping.source_document_id,
            target_document_id=mapping.target_document_id,
            source_version_id=mapping.source_version_id,
            target_version_id=mapping.target_version_id,
            mappings=list(mapping.mappings),
            unmatched_targets=list(mapping.unmatched_targets),
            metadata=metadata,
        )

    pair_rerank = rerank_fn if cfg.enable_reranker else None
    edges: list[tuple[NormalizedUnit, NormalizedUnit, float, MappingSignals]] = []
    candidate_total = 0
    rerank_calls = 0
    for source in sorted(review_sources, key=_unit_sort_key):
        ranked, used_rerank = _candidates_for(
            source,
            open_targets,
            vectors=vectors,
            parent_pairs=parent_pairs,
            config=cfg,
            rerank_fn=pair_rerank,
        )
        candidate_total += len(ranked)
        rerank_calls += used_rerank
        for target, score, signals in ranked:
            edges.append((source, target, score, signals))

    resolved, stats = _resolve_edges(
        review_sources,
        edges,
        config=cfg,
        parent_pairs=parent_pairs,
        source_version_id=mapping.source_version_id,
        target_version_id=mapping.target_version_id,
    )
    used_target_ids = {
        id(row.target_unit)
        for row in list(accepted) + resolved
        if row.accepted and row.target_unit is not None
    }
    unmatched_targets = [
        row
        for row in mapping.unmatched_targets
        if row.target_unit is None or id(row.target_unit) not in used_target_ids
    ]
    leftover_targets = [
        unit
        for unit in open_targets
        if id(unit) not in used_target_ids
        and all(
            row.target_unit is None or id(row.target_unit) != id(unit)
            for row in unmatched_targets
        )
    ]
    for unit in leftover_targets:
        unmatched_targets.append(
            _unmatched_target(unit, version_id=mapping.target_version_id)
        )

    semantic_meta.update(
        {
            "semantic_candidate_requests": len(review_sources),
            "semantic_candidates_generated": candidate_total,
            "semantic_accepted": stats["accepted"],
            "semantic_ambiguous": stats["ambiguous"],
            "semantic_unmatched": stats["unmatched"],
            "semantic_reranker_calls": rerank_calls,
            "semantic_cache_hits": store.hits,
            "semantic_cache_misses": store.misses,
            "semantic_latency_ms": int((time.perf_counter() - started) * 1000),
            "average_semantic_candidates": round(
                candidate_total / max(1, len(review_sources)), 3
            ),
        }
    )
    metadata.update(semantic_meta)
    return MappingResult(
        source_document_id=mapping.source_document_id,
        target_document_id=mapping.target_document_id,
        source_version_id=mapping.source_version_id,
        target_version_id=mapping.target_version_id,
        mappings=accepted + resolved,
        unmatched_targets=unmatched_targets,
        metadata=metadata,
    )


def _open_targets(
    mapping: MappingResult,
    review: Sequence[ClauseMapping],
    locked_targets: set[int],
) -> list[NormalizedUnit]:
    found: list[NormalizedUnit] = []
    seen: set[int] = set()

    def add(unit: NormalizedUnit | None) -> None:
        if unit is None or id(unit) in locked_targets or id(unit) in seen:
            return
        seen.add(id(unit))
        found.append(unit)

    for row in mapping.unmatched_targets:
        add(row.target_unit)
    for row in review:
        add(row.target_unit)
    return found


def _embed_units(
    units: Sequence[NormalizedUnit],
    *,
    embed_fn: EmbedFn,
    cache: EmbeddingCache,
    config: SemanticMatchConfig,
) -> tuple[dict[int, list[float]] | None, bool]:
    texts = [embedding_text(unit, max_chars=config.max_embedding_chars) for unit in units]
    try:
        vectors = cache.get_or_embed(texts, embed_fn)
    except Exception:  # noqa: BLE001 — semantic failure must not drop CMP-03
        return None, True
    if len(vectors) != len(units):
        return None, True
    return {id(unit): vector for unit, vector in zip(units, vectors, strict=True)}, False


def _candidates_for(
    source: NormalizedUnit,
    targets: Sequence[NormalizedUnit],
    *,
    vectors: dict[int, list[float]],
    parent_pairs: dict[str, str],
    config: SemanticMatchConfig,
    rerank_fn: RerankFn | None,
) -> tuple[list[tuple[NormalizedUnit, float, MappingSignals]], int]:
    source_vec = vectors.get(id(source))
    pool: list[tuple[NormalizedUnit, float]] = []
    for target in targets:
        if not types_compatible(source, target):
            continue
        if abs(TYPE_LEVEL[source.type] - TYPE_LEVEL[target.type]) > 1:
            continue
        target_vec = vectors.get(id(target))
        semantic = 0.0
        if source_vec is not None and target_vec is not None:
            semantic = cosine_similarity(source_vec, target_vec)
        if semantic < config.semantic_candidate_min and not _cheap_keep(source, target):
            continue
        pool.append((target, semantic))
    pool.sort(key=lambda item: (-item[1], item[0].identity_key or item[0].source_id))
    top = pool[: config.top_k]
    scored: list[tuple[NormalizedUnit, float, MappingSignals]] = []
    rerank_calls = 0
    for target, semantic in top:
        rerank = None
        if rerank_fn is not None:
            try:
                rerank = float(
                    rerank_fn(
                        embedding_text(source, max_chars=config.max_embedding_chars),
                        embedding_text(target, max_chars=config.max_embedding_chars),
                    )
                )
                rerank_calls += 1
            except Exception:  # noqa: BLE001
                rerank = None
        _, signals = score_pair(
            source,
            target,
            parent_pairs=parent_pairs,
            semantic=semantic,
            reranker=rerank,
        )
        sibling = sibling_number_mismatch(source, target, parent_pairs=parent_pairs)
        score = combined_semantic_score(
            signals, config=config, sibling_mismatch=sibling
        )
        method = _semantic_method(signals, rerank is not None)
        signals = MappingSignals(
            number_match=signals.number_match,
            type_match=signals.type_match,
            parent_match=signals.parent_match,
            title_similarity=signals.title_similarity,
            lexical_similarity=signals.lexical_similarity,
            semantic_similarity=semantic,
            reranker_score=rerank,
            structural_position=signals.structural_position,
            relative_number_match=signals.relative_number_match,
            method=method,
        )
        scored.append((target, score, signals))
    scored.sort(key=lambda item: (-item[1], item[0].identity_key or item[0].source_id))
    return scored, rerank_calls


def _cheap_keep(source: NormalizedUnit, target: NormalizedUnit) -> bool:
    """Keep a structurally promising pair even if cosine is weak (hash embed)."""
    if source.folded_title and source.folded_title == target.folded_title:
        return True
    return last_number_part(source.canonical_number) == last_number_part(
        target.canonical_number
    ) and last_number_part(source.canonical_number) is not None


def _resolve_edges(
    sources: Sequence[NormalizedUnit],
    edges: Sequence[tuple[NormalizedUnit, NormalizedUnit, float, MappingSignals]],
    *,
    config: SemanticMatchConfig,
    parent_pairs: dict[str, str],
    source_version_id,
    target_version_id,
) -> tuple[list[ClauseMapping], dict[str, int]]:
    by_source: dict[int, list[tuple[NormalizedUnit, float, MappingSignals]]] = {
        id(unit): [] for unit in sources
    }
    for source, target, score, signals in edges:
        by_source.setdefault(id(source), []).append((target, score, signals))
    for items in by_source.values():
        items.sort(key=lambda item: (-item[1], item[0].identity_key or item[0].source_id))

    claimed_targets: set[int] = set()
    claimed_sources: set[int] = set()
    rows: list[ClauseMapping] = []
    stats = {"accepted": 0, "ambiguous": 0, "unmatched": 0}

    ranked_sources = sorted(
        sources,
        key=lambda unit: (
            -(by_source.get(id(unit), [(None, 0.0, None)])[0][1] if by_source.get(id(unit)) else 0.0),
            unit.identity_key or unit.source_id,
        ),
    )
    for source in ranked_sources:
        options = [
            item
            for item in by_source.get(id(source), [])
            if id(item[0]) not in claimed_targets
        ]
        if not options:
            rows.append(
                _unmatched_source(source, version_id=source_version_id)
            )
            stats["unmatched"] += 1
            claimed_sources.add(id(source))
            continue
        best_target, best_score, best_signals = options[0]
        second = options[1][1] if len(options) > 1 else None
        margin = None if second is None else best_score - second
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
        candidates = [
            MappingCandidate(
                target_source_id=item[0].source_id,
                target_identity_key=item[0].identity_key,
                confidence=item[1],
                signals=item[2],
            )
            for item in options[: config.top_k]
        ]
        accept = can_accept_semantic(
            best_score,
            signals,
            margin=margin,
            config=config,
            sibling_mismatch=sibling_number_mismatch(
                source,
                best_target,
                parent_pairs=parent_pairs,
            ),
        )
        strong_second = (
            second is not None
            and second >= config.accept_min
            and margin is not None
            and margin < config.min_margin
        )
        if strong_second:
            rows.append(
                ClauseMapping(
                    source_unit=source,
                    target_unit=None,
                    mapping_type=MappingType.ONE_TO_MANY_CANDIDATE,
                    confidence=best_score,
                    confidence_level=MappingStatus.AMBIGUOUS,
                    signals=signals,
                    source_ref=clause_ref(source, version_id=source_version_id),
                    target_ref=None,
                    candidates=candidates,
                )
            )
            stats["ambiguous"] += 1
            claimed_sources.add(id(source))
            continue
        if accept:
            level = MappingStatus(config.classify(best_score))
            if level not in {
                MappingStatus.HIGH_CONFIDENCE,
                MappingStatus.MEDIUM_CONFIDENCE,
            }:
                level = MappingStatus.MEDIUM_CONFIDENCE
            rows.append(
                ClauseMapping(
                    source_unit=source,
                    target_unit=best_target,
                    mapping_type=MappingType.SEMANTIC,
                    confidence=best_score,
                    confidence_level=level,
                    signals=signals,
                    source_ref=clause_ref(source, version_id=source_version_id),
                    target_ref=clause_ref(best_target, version_id=target_version_id),
                    candidates=candidates,
                )
            )
            stats["accepted"] += 1
            claimed_sources.add(id(source))
            claimed_targets.add(id(best_target))
            continue
        level = MappingStatus(config.classify(best_score))
        if level is MappingStatus.LOW_CONFIDENCE:
            rows.append(
                ClauseMapping(
                    source_unit=source,
                    target_unit=best_target,
                    mapping_type=MappingType.SEMANTIC,
                    confidence=best_score,
                    confidence_level=MappingStatus.LOW_CONFIDENCE,
                    signals=signals,
                    source_ref=clause_ref(source, version_id=source_version_id),
                    target_ref=clause_ref(best_target, version_id=target_version_id),
                    candidates=candidates,
                )
            )
        else:
            rows.append(
                _unmatched_source(
                    source,
                    version_id=source_version_id,
                    candidates=candidates,
                    signals=signals,
                    confidence=best_score,
                )
            )
        stats["unmatched"] += 1
        claimed_sources.add(id(source))

    for source in sources:
        if id(source) not in claimed_sources:
            rows.append(_unmatched_source(source, version_id=source_version_id))
            stats["unmatched"] += 1
    return rows, stats


def _semantic_method(signals: MappingSignals, used_rerank: bool) -> str:
    if used_rerank:
        return "semantic_rerank"
    if signals.parent_match:
        return "semantic_parent"
    return "semantic"


def _unit_sort_key(unit: NormalizedUnit) -> tuple[str, str]:
    return (unit.identity_key or "", unit.source_id)


def _unmatched_source(
    source: NormalizedUnit,
    *,
    version_id,
    candidates: list[MappingCandidate] | None = None,
    signals: MappingSignals | None = None,
    confidence: float = 0.0,
) -> ClauseMapping:
    return ClauseMapping(
        source_unit=source,
        target_unit=None,
        mapping_type=MappingType.ONE_TO_ONE,
        confidence=confidence,
        confidence_level=MappingStatus.UNMATCHED,
        signals=signals
        or MappingSignals(
            number_match=False,
            type_match=False,
            parent_match=False,
            title_similarity=0.0,
            lexical_similarity=0.0,
            method="unmatched",
        ),
        source_ref=clause_ref(source, version_id=version_id),
        target_ref=None,
        candidates=candidates or [],
    )


def _unmatched_target(target: NormalizedUnit, *, version_id) -> ClauseMapping:
    return ClauseMapping(
        source_unit=None,
        target_unit=target,
        mapping_type=MappingType.ONE_TO_ONE,
        confidence=0.0,
        confidence_level=MappingStatus.UNMATCHED,
        signals=MappingSignals(
            number_match=False,
            type_match=False,
            parent_match=False,
            title_similarity=0.0,
            lexical_similarity=0.0,
            method="unmatched",
        ),
        source_ref=None,
        target_ref=clause_ref(target, version_id=version_id),
    )
