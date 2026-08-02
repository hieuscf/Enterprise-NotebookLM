# =============================================================================
# File: test_query_classifier.py
# Module/Service: Query Router — Rule-based Classifier (FR11)
# Layer: Service
# Purpose: Unit tests for normalize, metadata patterns, embedding centroid path.
# Responsibilities:
#   - Metadata / factoid / complex samples (VI+EN); normalize; priority; margin
# Dependencies:
#   - pytest, numpy, app.services.query_router.*
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: RuleBasedClassifier, QueryClassifier Protocol
# Important Notes: 0 LLM; uses HashingNgramEmbeddingProvider / FakeEmbeddingProvider.
# =============================================================================

from __future__ import annotations

import uuid
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from app.models.enums import RouteType
from app.services.query_router.classifier import QueryClassifier, RuleBasedClassifier
from app.services.query_router.config import ClassifierConfig, default_examples_dir
from app.services.query_router.embedding_provider import HashingNgramEmbeddingProvider
from app.services.query_router.metadata_patterns import (
    DEFAULT_METADATA_RULES,
    MetadataPatternRegistry,
    PatternRule,
)
from app.services.query_router.normalizer import normalize_query
from app.services.query_router.rule_classifier import build_rule_based_classifier

WS = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeEmbeddingProvider:
    """Deterministic provider mapping substrings → fixed vectors for tests."""

    def __init__(self, mapping: dict[str, NDArray[np.float64]], dim: int = 4) -> None:
        self._mapping = {normalize_query(k): v for k, v in mapping.items()}
        self._dim = dim
        self.embed_calls = 0

    def embed(self, texts: list[str]) -> NDArray[np.float64]:
        self.embed_calls += 1
        rows: list[NDArray[np.float64]] = []
        for text in texts:
            key = normalize_query(text)
            if key in self._mapping:
                rows.append(self._mapping[key])
                continue
            # Heuristic: factoid-ish vs complex-ish tokens for examples + queries.
            if any(
                tok in key
                for tok in ("what", "who", "when", "where", "là gì", "là ai", "khi nào")
            ) and not any(
                tok in key for tok in ("compare", "summarize", "analyze", "so sánh", "tóm tắt")
            ):
                rows.append(np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float64))
            elif any(
                tok in key
                for tok in (
                    "compare",
                    "summarize",
                    "explain",
                    "analyze",
                    "why",
                    "difference",
                    "so sánh",
                    "tóm tắt",
                    "phân tích",
                    "giải thích",
                    "tại sao",
                )
            ):
                rows.append(np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float64))
            else:
                rows.append(np.array([0.5, 0.5, 0.0, 0.0], dtype=np.float64))
        return np.vstack(rows)


def _config(
    *,
    confidence: float = 0.10,
    margin: float = 0.05,
    dim: int = 4,
    examples_dir: Path | None = None,
) -> ClassifierConfig:
    return ClassifierConfig(
        confidence_threshold=confidence,
        margin_threshold=margin,
        embedding_dimension=dim,
        examples_dir=examples_dir or default_examples_dir(),
    )


def _classifier(
    *,
    embedding: FakeEmbeddingProvider | HashingNgramEmbeddingProvider | None = None,
    confidence: float = 0.10,
    margin: float = 0.03,
    patterns: MetadataPatternRegistry | None = None,
) -> RuleBasedClassifier:
    provider: FakeEmbeddingProvider | HashingNgramEmbeddingProvider
    if embedding is None:
        provider = HashingNgramEmbeddingProvider(dimension=256)
    else:
        provider = embedding
    return RuleBasedClassifier(
        config=_config(
            confidence=confidence,
            margin=margin,
            dim=getattr(provider, "dimension", 256)
            if not isinstance(provider, FakeEmbeddingProvider)
            else 4,
        ),
        embedding=provider,
        patterns=patterns,
    )


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


def test_normalize_lowercase_punctuation_whitespace() -> None:
    assert normalize_query("What is Apple's CEO?") == "what is apple ceo"


def test_normalize_unicode_and_collapse() -> None:
    assert normalize_query("  Có   BAO\tnhiều!!!  ") == "có bao nhiều"


def test_normalize_empty() -> None:
    assert normalize_query("") == ""
    assert normalize_query("   ") == ""


# ---------------------------------------------------------------------------
# Metadata (>=5) — VI + EN
# ---------------------------------------------------------------------------

METADATA_SAMPLES = [
    "Có bao nhiêu tài liệu",
    "Danh sách PDF",
    "Show all files",
    "Latest documents",
    "Count invoices",
    "How many documents",
    "File mới nhất",
    "Who uploaded this file",
    "Liệt kê các PDF",
    "Hiển thị workspace",
]


@pytest.mark.parametrize("query", METADATA_SAMPLES)
def test_metadata_classification(query: str) -> None:
    clf = _classifier()
    assert clf.classify(query, WS) == RouteType.metadata


def test_metadata_case_and_punctuation() -> None:
    clf = _classifier()
    assert clf.classify("  HOW MANY   DOCUMENTS??? ", WS) == RouteType.metadata


def test_metadata_always_before_embedding() -> None:
    """Metadata must short-circuit — no query embed after centroids are warm."""
    provider = HashingNgramEmbeddingProvider(dimension=64)
    call_count = {"n": 0}
    original = provider.embed

    def counting_embed(texts: list[str]) -> NDArray[np.float64]:
        call_count["n"] += 1
        return original(texts)

    provider.embed = counting_embed  # type: ignore[method-assign]
    clf = _classifier(embedding=provider)
    clf.classify("What is the warranty period?", WS)
    before = call_count["n"]
    assert clf.classify("Có bao nhiêu tài liệu?", WS) == RouteType.metadata
    assert call_count["n"] == before


def test_metadata_priority_registry() -> None:
    rules = (
        PatternRule(name="low", priority=10, keywords=("documents",)),
        PatternRule(name="high", priority=200, keywords=("how many documents",)),
    )
    registry = MetadataPatternRegistry(rules=rules)
    match = registry.match(normalize_query("How many documents are there?"))
    assert match.matched
    assert match.rule_name == "high"


def test_default_metadata_rules_not_empty() -> None:
    assert len(DEFAULT_METADATA_RULES) >= 4


# ---------------------------------------------------------------------------
# Factoid (>=5)
# ---------------------------------------------------------------------------

FACTOID_SAMPLES = [
    "What is the warranty period?",
    "Who signed the contract?",
    "What is invoice number?",
    "Where is company address?",
    "When was this document created?",
    "AI là gì?",
    "Tác giả là ai?",
    "What is RAG?",
]


@pytest.mark.parametrize("query", FACTOID_SAMPLES)
def test_factoid_classification(query: str) -> None:
    clf = _classifier()
    assert clf.classify(query, WS) == RouteType.factoid


def test_factoid_mixed_case_punctuation() -> None:
    clf = _classifier()
    assert clf.classify("WHAT IS The Warranty Period?!!", WS) == RouteType.factoid


# ---------------------------------------------------------------------------
# Complex (>=5)
# ---------------------------------------------------------------------------

COMPLEX_SAMPLES = [
    "Compare policy A and B",
    "Summarize report",
    "Explain root cause",
    "Analyze trends",
    "Why revenue decreased",
    "So sánh hai chính sách nghỉ phép",
    "Tóm tắt toàn bộ tài liệu và đưa ra khuyến nghị",
    "Phân tích ưu nhược điểm của kiến trúc RAG",
]


@pytest.mark.parametrize("query", COMPLEX_SAMPLES)
def test_complex_classification(query: str) -> None:
    clf = _classifier()
    assert clf.classify(query, WS) == RouteType.complex


# ---------------------------------------------------------------------------
# Confidence / margin fallback
# ---------------------------------------------------------------------------


def test_low_margin_falls_back_to_complex() -> None:
    # Identical vectors for both classes → margin 0 → complex.
    same = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)

    class FlatProvider:
        def embed(self, texts: list[str]) -> NDArray[np.float64]:
            return np.vstack([same for _ in texts])

    clf = RuleBasedClassifier(
        config=_config(confidence=0.0, margin=0.05, dim=8),
        embedding=FlatProvider(),
    )
    result = clf.classify_detailed("some ambiguous query xyz", WS)
    assert result.route_type == RouteType.complex
    assert result.margin is not None and result.margin < 0.05
    assert "low_margin" in result.reason


def test_low_confidence_falls_back_to_complex() -> None:
    factoid_v = np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
    complex_v = np.array([0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
    # Query nearly orthogonal to both → low confidence.
    query_v = np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)

    class OrthProvider:
        def embed(self, texts: list[str]) -> NDArray[np.float64]:
            rows: list[NDArray[np.float64]] = []
            for t in texts:
                n = normalize_query(t)
                if "orthogonal_unique_query" in n:
                    rows.append(query_v)
                elif any(x in n for x in ("compare", "summarize", "analyze", "why", "explain")):
                    rows.append(complex_v)
                else:
                    rows.append(factoid_v)
            return np.vstack(rows)

    clf = RuleBasedClassifier(
        config=_config(confidence=0.50, margin=0.0, dim=8),
        embedding=OrthProvider(),
    )
    result = clf.classify_detailed("orthogonal_unique_query_zzz", WS)
    assert result.route_type == RouteType.complex
    assert "low_confidence" in result.reason


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_never_returns_cache_hit() -> None:
    clf = build_rule_based_classifier()
    samples = METADATA_SAMPLES + FACTOID_SAMPLES + COMPLEX_SAMPLES + ["", "???"]
    for q in samples:
        assert clf.classify(q, WS) != RouteType.cache_hit


def test_implements_protocol() -> None:
    clf = build_rule_based_classifier()
    assert isinstance(clf, QueryClassifier)


def test_centroid_cache_singleton() -> None:
    provider = HashingNgramEmbeddingProvider(dimension=64)
    call_count = {"n": 0}
    original = provider.embed

    def counting_embed(texts: list[str]) -> NDArray[np.float64]:
        call_count["n"] += 1
        return original(texts)

    provider.embed = counting_embed  # type: ignore[method-assign]
    clf = _classifier(embedding=provider)
    clf.classify("What is RAG?", WS)
    after_first = call_count["n"]
    assert after_first >= 2  # examples batch + query
    clf.classify("Who is the author?", WS)
    # Second classify embeds only the query once (examples cached).
    assert call_count["n"] == after_first + 1


def test_empty_query_is_complex() -> None:
    clf = _classifier()
    assert clf.classify("   ", WS) == RouteType.complex


def test_hashing_provider_dimension() -> None:
    provider = HashingNgramEmbeddingProvider(dimension=32)
    mat = provider.embed(["hello world", "hello world"])
    assert mat.shape == (2, 32)
    # Deterministic.
    assert np.allclose(mat[0], mat[1])


def test_examples_files_exist() -> None:
    root = default_examples_dir()
    assert (root / "factoid.json").is_file()
    assert (root / "complex.json").is_file()
