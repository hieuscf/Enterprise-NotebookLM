# =============================================================================
# File: taxonomy_engine.py
# Module/Service: Legal Risk Taxonomy (FR8 / TASK-CMP-07)
# Layer: Service
# Purpose: Classify mapped clause diffs into the 14-category legal taxonomy.
# Responsibilities:
#   - Title > parent heading > local exact-change context > body phrases
#   - Primary + secondary categories; OTHER when signals are weak/ambiguous
#   - Preserve ClauseRef; never assign risk_level; 0 LLM
# Dependencies:
#   - taxonomy_types, taxonomy_config, taxonomy_rules
#   - exact_types.ExactChange; diff_types; patterns.fold_ocr_text
# Public Exports:
#   - classify_taxonomy, classify_clause_diff
# Database/Table: N/A
# Related Modules: LegalRiskTaxonomyEngine; CMP-08 consumes TaxonomyAssignment
# Important Notes:
#   - value_type ≠ category. Article numbers never select a category.
#   - Exceptions degrade to OTHER / FALLBACK (no stack traces in the result).
# =============================================================================

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from app.ai.document_structure.diff_types import (
    ClauseDiff,
    DiffClassification,
    DiffResult,
)
from app.ai.document_structure.exact_types import ExactChange, ExactDiffResult
from app.ai.document_structure.normalization import NormalizedUnit
from app.ai.document_structure.patterns import fold_ocr_text
from app.ai.document_structure.taxonomy_config import TaxonomyConfig
from app.ai.document_structure.taxonomy_rules import TAXONOMY_RULES, TaxonomyRule
from app.ai.document_structure.taxonomy_types import (
    RISK_LEVEL_UNSET,
    TAXONOMY_VERSION,
    ClassificationConfidence,
    ClassificationMethod,
    ClassificationStatus,
    RiskCategory,
    TIE_BREAK,
    TaxonomyAssignment,
    TaxonomyResult,
)

@dataclass(frozen=True, slots=True)
class _Hit:
    category: RiskCategory
    score: float
    rule: TaxonomyRule
    signal: str
    layer: str


_SKIP = frozenset(
    {
        DiffClassification.UNCHANGED,
        DiffClassification.AMBIGUOUS_MAPPING,
        DiffClassification.UNKNOWN,
    }
)
_SPACE = re.compile(r"\s+")
_ADVICE = re.compile(
    r"legally dangerous|you should reject|high risk|critical risk|unfavorable",
    re.I,
)


def classify_taxonomy(
    diff: DiffResult,
    exact: ExactDiffResult | None = None,
    *,
    config: TaxonomyConfig | None = None,
) -> TaxonomyResult:
    """Classify every non-unchanged clause row. Does not remap or score risk."""
    started = time.perf_counter()
    cfg = config or TaxonomyConfig()
    by_identity = _index_diffs(diff)
    changes_by_key = _index_changes(exact)
    rows: list[TaxonomyAssignment] = []
    fallback = 0
    review = 0
    for item in diff.diffs:
        if item.classification in _SKIP:
            continue
        try:
            assignment = classify_clause_diff(
                item,
                changes=_changes_for(item, changes_by_key),
                parent_title=_parent_title(item, by_identity),
                config=cfg,
            )
        except Exception:
            assignment = _fallback(item, cfg, rule_id="other.engine_error")
        if assignment.classification_status is ClassificationStatus.NEEDS_REVIEW:
            review += 1
        if assignment.classification_method is ClassificationMethod.FALLBACK:
            fallback += 1
        rows.append(assignment)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return TaxonomyResult(
        source_document_id=diff.source_document_id,
        target_document_id=diff.target_document_id,
        source_version_id=diff.source_version_id,
        target_version_id=diff.target_version_id,
        assignments=rows,
        taxonomy_version=cfg.taxonomy_version,
        metadata=_metadata(rows, fallback=fallback, review=review, duration_ms=duration_ms),
    )


def classify_clause_diff(
    item: ClauseDiff,
    *,
    changes: list[ExactChange] | None = None,
    parent_title: str = "",
    config: TaxonomyConfig | None = None,
) -> TaxonomyAssignment:
    """Classify one CMP-04 row using title, parent, local context, and body."""
    cfg = config or TaxonomyConfig()
    fields = _fields(item, changes or [], parent_title)
    scored = _score(fields, cfg)
    return _resolve(item, changes or [], scored, cfg)


def _fields(
    item: ClauseDiff,
    changes: list[ExactChange],
    parent_title: str,
) -> dict[str, str]:
    source = item.source_unit
    target = item.target_unit
    title = " ".join(
        part
        for part in (
            _unit_title(target),
            _unit_title(source),
        )
        if part
    )
    heading = " ".join(
        part
        for part in (
            target.heading_path if target else "",
            source.heading_path if source else "",
        )
        if part
    )
    body = " ".join(
        part
        for part in (
            _unit_body(target),
            _unit_body(source),
        )
        if part
    )
    local = " ".join(
        part
        for part in [
            *(change.context for change in changes if change.context),
            *(
                (change.old_value.sentence if change.old_value else "")
                for change in changes
            ),
            *(
                (change.new_value.sentence if change.new_value else "")
                for change in changes
            ),
            *(snippet.old + " " + snippet.new for snippet in item.sentence_changes),
        ]
        if part
    )
    return {
        "title": _fold(title),
        "parent": _fold(parent_title),
        "heading": _fold(heading),
        "local": _fold(local),
        "body": _fold(body),
    }


def _score(
    fields: dict[str, str],
    config: TaxonomyConfig,
) -> dict[RiskCategory, _Hit]:
    hits: dict[RiskCategory, _Hit] = {}
    layers = (
        ("title", config.title_weight),
        ("parent", config.parent_weight),
        ("heading", config.parent_weight),
        ("local", config.local_weight),
        ("body", config.body_weight),
    )
    for layer, layer_weight in layers:
        text = fields.get(layer) or ""
        if not text:
            continue
        for rule in TAXONOMY_RULES:
            signal = rule.match(text)
            if not signal:
                continue
            score = rule.weight * layer_weight
            current = hits.get(rule.category)
            if current is None or score > current.score:
                hits[rule.category] = _Hit(
                    category=rule.category,
                    score=score,
                    rule=rule,
                    signal=signal,
                    layer=layer,
                )
    return hits


def _resolve(
    item: ClauseDiff,
    changes: list[ExactChange],
    hits: dict[RiskCategory, _Hit],
    config: TaxonomyConfig,
) -> TaxonomyAssignment:
    ranked = sorted(
        (hit for hit in hits.values() if hit.category is not RiskCategory.OTHER),
        key=lambda hit: (-hit.score, TIE_BREAK.index(hit.category)),
    )
    title_hit = next((hit for hit in ranked if hit.layer == "title"), None)
    if title_hit and title_hit.score >= config.title_override_min:
        primary = title_hit
    elif not ranked or ranked[0].score < config.accept_min:
        return _assignment(
            item,
            changes,
            category=RiskCategory.OTHER,
            secondary=(),
            score=ranked[0].score if ranked else 0.0,
            confidence=ClassificationConfidence.LOW,
            method=ClassificationMethod.FALLBACK,
            status=ClassificationStatus.OTHER,
            rule_id="other.fallback",
            signals=(),
            config=config,
        )
    else:
        primary = ranked[0]
        runner = ranked[1] if len(ranked) > 1 else None
        if (
            runner
            and runner.score >= config.accept_min
            and (primary.score - runner.score) < config.ambiguous_margin
            and primary.layer not in {"title", "parent"}
            and runner.layer not in {"title", "parent"}
        ):
            return _assignment(
                item,
                changes,
                category=RiskCategory.OTHER,
                secondary=(),
                score=primary.score,
                confidence=ClassificationConfidence.LOW,
                method=ClassificationMethod.FALLBACK,
                status=ClassificationStatus.NEEDS_REVIEW,
                rule_id="other.ambiguous",
                signals=(primary.signal, runner.signal),
                config=config,
            )

    secondary = tuple(
        hit.category
        for hit in ranked
        if hit.category is not primary.category and hit.score >= config.secondary_min
    )
    status = ClassificationStatus.CLASSIFIED
    method = ClassificationMethod.RULE
    confidence = _confidence(primary.score, config)
    return _assignment(
        item,
        changes,
        category=primary.category,
        secondary=secondary,
        score=primary.score,
        confidence=confidence,
        method=method,
        status=status,
        rule_id=primary.rule.rule_id,
        signals=_signals(primary, ranked),
        config=config,
    )


def _assignment(
    item: ClauseDiff,
    changes: list[ExactChange],
    *,
    category: RiskCategory,
    secondary: tuple[RiskCategory, ...],
    score: float,
    confidence: ClassificationConfidence,
    method: ClassificationMethod,
    status: ClassificationStatus,
    rule_id: str,
    signals: tuple[str, ...],
    config: TaxonomyConfig,
) -> TaxonomyAssignment:
    identity = _identity(item)
    value_types = tuple(dict.fromkeys(change.value_type for change in changes))
    return TaxonomyAssignment(
        primary_category=category,
        secondary_categories=secondary,
        classification_confidence=confidence,
        confidence_score=score,
        classification_method=method,
        classification_status=status,
        taxonomy_version=config.taxonomy_version,
        rule_id=rule_id,
        matched_signals=signals,
        source_ref=item.source_ref,
        target_ref=item.target_ref,
        identity_key=identity,
        diff_classification=item.classification,
        value_types=value_types,
        risk_level=RISK_LEVEL_UNSET,
    )


def _fallback(item: ClauseDiff, config: TaxonomyConfig, *, rule_id: str) -> TaxonomyAssignment:
    return _assignment(
        item,
        [],
        category=RiskCategory.OTHER,
        secondary=(),
        score=0.0,
        confidence=ClassificationConfidence.LOW,
        method=ClassificationMethod.FALLBACK,
        status=ClassificationStatus.OTHER,
        rule_id=rule_id,
        signals=(),
        config=config,
    )


def _confidence(score: float, config: TaxonomyConfig) -> ClassificationConfidence:
    if score >= config.high_confidence_min:
        return ClassificationConfidence.HIGH
    if score >= config.medium_confidence_min:
        return ClassificationConfidence.MEDIUM
    return ClassificationConfidence.LOW


def _signals(primary: _Hit, ranked: list[_Hit]) -> tuple[str, ...]:
    seen: list[str] = []
    for hit in (primary, *ranked):
        if hit.signal and hit.signal not in seen:
            seen.append(hit.signal)
        if len(seen) >= 6:
            break
    return tuple(seen)


def _index_diffs(diff: DiffResult) -> dict[str, ClauseDiff]:
    index: dict[str, ClauseDiff] = {}
    for item in diff.diffs:
        if item.source_unit and item.source_unit.identity_key:
            index[item.source_unit.identity_key] = item
        if item.target_unit and item.target_unit.identity_key:
            index.setdefault(item.target_unit.identity_key, item)
    return index


def _index_changes(exact: ExactDiffResult | None) -> dict[str, list[ExactChange]]:
    grouped: dict[str, list[ExactChange]] = {}
    if exact is None:
        return grouped
    for change in exact.changes:
        for ref in (change.source_ref, change.target_ref):
            if ref and ref.identity_key:
                grouped.setdefault(ref.identity_key, []).append(change)
                break
    return grouped


def _changes_for(
    item: ClauseDiff,
    grouped: dict[str, list[ExactChange]],
) -> list[ExactChange]:
    keys = []
    if item.source_unit and item.source_unit.identity_key:
        keys.append(item.source_unit.identity_key)
    if item.target_unit and item.target_unit.identity_key:
        keys.append(item.target_unit.identity_key)
    rows: list[ExactChange] = []
    seen: set[int] = set()
    for key in keys:
        for change in grouped.get(key, []):
            marker = id(change)
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(change)
    return rows


def _parent_title(item: ClauseDiff, index: dict[str, ClauseDiff]) -> str:
    titles: list[str] = []
    for unit in (item.source_unit, item.target_unit):
        if unit is None or not unit.parent_identity_key:
            continue
        parent = index.get(unit.parent_identity_key)
        if parent is None:
            continue
        for parent_unit in (parent.source_unit, parent.target_unit):
            title = _unit_title(parent_unit)
            if title:
                titles.append(title)
    return " ".join(titles)


def _unit_title(unit: NormalizedUnit | None) -> str:
    if unit is None:
        return ""
    return " ".join(
        part
        for part in (unit.original_title, unit.original_heading, unit.normalized_title)
        if part
    )


def _unit_body(unit: NormalizedUnit | None) -> str:
    if unit is None:
        return ""
    return unit.original_text or unit.normalized_body or ""


def _identity(item: ClauseDiff) -> str | None:
    if item.source_unit and item.source_unit.identity_key:
        return item.source_unit.identity_key
    if item.target_unit and item.target_unit.identity_key:
        return item.target_unit.identity_key
    return None


def _fold(text: str) -> str:
    return _SPACE.sub(" ", fold_ocr_text(text).casefold()).strip()


def _metadata(
    rows: list[TaxonomyAssignment],
    *,
    fallback: int,
    review: int,
    duration_ms: int,
) -> dict[str, Any]:
    counts = {item.value: 0 for item in RiskCategory}
    multi = 0
    for row in rows:
        counts[row.primary_category.value] += 1
        if row.secondary_categories:
            multi += 1
    return {
        "taxonomy_version": TAXONOMY_VERSION,
        "clauses_processed": len(rows),
        "classification_count": len(rows),
        "category_counts": counts,
        "other_count": counts[RiskCategory.OTHER.value],
        "low_confidence_count": sum(
            1
            for row in rows
            if row.classification_confidence is ClassificationConfidence.LOW
        ),
        "rule_match_count": sum(
            1 for row in rows if row.classification_method is ClassificationMethod.RULE
        ),
        "fallback_count": fallback,
        "needs_review_count": review,
        "multi_category_count": multi,
        "taxonomy_latency_ms": duration_ms,
        "taxonomy_llm_calls": 0,
        "advice_leak": any(
            _ADVICE.search(" ".join(row.matched_signals)) for row in rows
        ),
    }
