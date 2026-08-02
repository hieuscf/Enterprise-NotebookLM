# =============================================================================
# File: rule_classifier.py
# Module/Service: Query Router — Rule-based Classifier (FR11)
# Layer: Service
# Purpose: Metadata-first + embedding centroid few-shot classification (0 LLM).
# Responsibilities:
#   - Normalize → metadata PatternRule match → centroid cosine (factoid/complex)
#   - Lazy singleton embedding of example sets; confidence / margin fallback
# Dependencies:
#   - QueryClassifier, ClassifierConfig, EmbeddingProvider, MetadataPatternRegistry
# Public Exports:
#   - RuleBasedClassifier, build_rule_based_classifier
# Database/Table: N/A
# Related Modules: app.services.query_router.router, classifier
# Important Notes:
#   - Never returns RouteType.cache_hit.
#   - No FAISS / ANN / KNN / LLM — only centroid + cosine similarity.
# =============================================================================

from __future__ import annotations

import json
import threading
from pathlib import Path
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.enums import RouteType
from app.services.query_router.config import ClassifierConfig, build_classifier_config
from app.services.query_router.embedding_provider import (
    EmbeddingProvider,
    HashingNgramEmbeddingProvider,
)
from app.services.query_router.metadata_patterns import (
    MetadataPatternRegistry,
)
from app.services.query_router.models import ClassificationResult
from app.services.query_router.normalizer import normalize_query

logger = get_logger(__name__)

_FACTOID_FILE = "factoid.json"
_COMPLEX_FILE = "complex.json"
_CLASS_FACTOID = "factoid"
_CLASS_COMPLEX = "complex"


def _cosine_similarity(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """Cosine similarity between two 1-D vectors."""
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _load_examples(path: Path) -> list[str]:
    """Load a JSON list of example query strings from ``path``."""
    if not path.is_file():
        raise FileNotFoundError(f"Classifier examples not found: {path}")
    with path.open(encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if not isinstance(data, list) or not data:
        raise ValueError(f"Examples file must be a non-empty JSON list: {path}")
    out: list[str] = []
    for item in data:
        if not isinstance(item, str) or not item.strip():
            continue
        out.append(item.strip())
    if not out:
        raise ValueError(f"No valid string examples in {path}")
    return out


class RuleBasedClassifier:
    """Production rule + embedding few-shot classifier implementing ``QueryClassifier``.

    Pipeline:
      1. Normalize query
      2. Metadata pattern registry (priority) — early return on match
      3. Embed query; cosine to factoid / complex centroids
      4. If confidence or margin below config thresholds → ``complex``
    """

    def __init__(
        self,
        *,
        config: ClassifierConfig,
        embedding: EmbeddingProvider,
        patterns: MetadataPatternRegistry | None = None,
    ) -> None:
        self._config = config
        self._embedding = embedding
        self._patterns = patterns or MetadataPatternRegistry()
        self._lock = threading.Lock()
        self._centroids: dict[str, NDArray[np.float64]] | None = None

    # ------------------------------------------------------------------
    # Public QueryClassifier API
    # ------------------------------------------------------------------

    def classify(self, query_text: str, workspace_id: UUID) -> RouteType:
        """Classify into metadata / factoid / complex (never ``cache_hit``).

        Args:
            query_text: Raw user question.
            workspace_id: Tenant id (reserved; unused — no side effects).

        Returns:
            Non-cache ``RouteType``.
        """
        result = self.classify_detailed(query_text, workspace_id)
        return result.route_type

    def classify_detailed(
        self,
        query_text: str,
        workspace_id: UUID,
    ) -> ClassificationResult:
        """Classify with confidence / margin / reason for logging.

        Args:
            query_text: Raw user question.
            workspace_id: Tenant id (accepted for interface symmetry).

        Returns:
            ``ClassificationResult`` whose ``route_type`` is never ``cache_hit``.
        """
        _ = workspace_id  # reserved for future per-workspace pattern overlays
        normalized = normalize_query(query_text)
        if not normalized:
            return ClassificationResult(
                route_type=RouteType.complex,
                reason="empty_query_default_complex",
                confidence=None,
                margin=None,
            )

        meta = self._patterns.match(normalized)
        if meta.matched:
            logger.info(
                "query_classifier_metadata",
                rule=meta.rule_name,
                pattern=meta.pattern,
                priority=meta.priority,
            )
            return ClassificationResult(
                route_type=RouteType.metadata,
                reason=f"metadata_rule={meta.rule_name};pattern={meta.pattern}",
                confidence=1.0,
                margin=None,
                metadata_rule=meta.rule_name,
            )

        return self._classify_embedding(normalized)

    # ------------------------------------------------------------------
    # Backward-compatible helpers (router / tests during migration)
    # ------------------------------------------------------------------

    def match_metadata(self, normalized_query: str):
        """Return metadata match for an already-normalized query (compat helper)."""
        return self._patterns.match(normalized_query)

    # ------------------------------------------------------------------
    # Embedding few-shot path
    # ------------------------------------------------------------------

    def _classify_embedding(self, normalized: str) -> ClassificationResult:
        centroids = self._ensure_centroids()
        query_vec = self._embedding.embed([normalized])[0]
        sim_factoid = _cosine_similarity(query_vec, centroids[_CLASS_FACTOID])
        sim_complex = _cosine_similarity(query_vec, centroids[_CLASS_COMPLEX])
        margin = abs(sim_factoid - sim_complex)

        if sim_factoid >= sim_complex:
            winner = RouteType.factoid
            confidence = sim_factoid
        else:
            winner = RouteType.complex
            confidence = sim_complex

        if confidence < self._config.confidence_threshold:
            logger.info(
                "query_classifier_low_confidence",
                confidence=confidence,
                threshold=self._config.confidence_threshold,
                sim_factoid=sim_factoid,
                sim_complex=sim_complex,
            )
            return ClassificationResult(
                route_type=RouteType.complex,
                reason=(
                    f"low_confidence:{confidence:.4f}<"
                    f"{self._config.confidence_threshold:.4f}"
                ),
                confidence=confidence,
                margin=margin,
            )

        if margin < self._config.margin_threshold:
            logger.info(
                "query_classifier_low_margin",
                margin=margin,
                threshold=self._config.margin_threshold,
                sim_factoid=sim_factoid,
                sim_complex=sim_complex,
            )
            return ClassificationResult(
                route_type=RouteType.complex,
                reason=(
                    f"low_margin:{margin:.4f}<"
                    f"{self._config.margin_threshold:.4f};fallback_complex"
                ),
                confidence=confidence,
                margin=margin,
            )

        logger.info(
            "query_classifier_embedding",
            route_type=winner.value,
            confidence=confidence,
            margin=margin,
            sim_factoid=sim_factoid,
            sim_complex=sim_complex,
        )
        return ClassificationResult(
            route_type=winner,
            reason=(
                f"embedding_centroid;winner={winner.value};"
                f"confidence={confidence:.4f};margin={margin:.4f}"
            ),
            confidence=confidence,
            margin=margin,
        )

    def _ensure_centroids(self) -> dict[str, NDArray[np.float64]]:
        """Lazy-load example embeddings and compute class centroids once."""
        if self._centroids is not None:
            return self._centroids
        with self._lock:
            if self._centroids is not None:
                return self._centroids
            self._centroids = self._compute_centroids()
            return self._centroids

    def _compute_centroids(self) -> dict[str, NDArray[np.float64]]:
        examples_dir = self._config.examples_dir
        factoid_raw = _load_examples(examples_dir / _FACTOID_FILE)
        complex_raw = _load_examples(examples_dir / _COMPLEX_FILE)
        factoid_norm = [normalize_query(t) for t in factoid_raw]
        complex_norm = [normalize_query(t) for t in complex_raw]

        factoid_vecs = self._embedding.embed(factoid_norm)
        complex_vecs = self._embedding.embed(complex_norm)
        centroids = {
            _CLASS_FACTOID: _mean_centroid(factoid_vecs),
            _CLASS_COMPLEX: _mean_centroid(complex_vecs),
        }
        logger.info(
            "query_classifier_centroids_ready",
            factoid_examples=len(factoid_norm),
            complex_examples=len(complex_norm),
            dimension=int(factoid_vecs.shape[1]) if factoid_vecs.size else 0,
        )
        return centroids

    def reset_centroid_cache(self) -> None:
        """Clear cached centroids (tests / hot-reload of examples)."""
        with self._lock:
            self._centroids = None


def _mean_centroid(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    """Mean row vector, L2-normalized."""
    if matrix.size == 0:
        raise ValueError("Cannot compute centroid of empty embedding matrix")
    centroid = np.mean(matrix, axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm > 0.0:
        centroid = centroid / norm
    return centroid.astype(np.float64, copy=False)


def build_rule_based_classifier(
    settings: Settings | None = None,
    *,
    embedding: EmbeddingProvider | None = None,
    patterns: MetadataPatternRegistry | None = None,
) -> RuleBasedClassifier:
    """Factory wiring config + default hashing embedding provider.

    Args:
        settings: Optional app settings.
        embedding: Optional injected provider (tests / alternate backends).
        patterns: Optional metadata registry override.

    Returns:
        Ready-to-use ``RuleBasedClassifier``.
    """
    cfg_settings = settings or get_settings()
    config = build_classifier_config(cfg_settings)
    provider = embedding or HashingNgramEmbeddingProvider(
        dimension=config.embedding_dimension,
    )
    return RuleBasedClassifier(
        config=config,
        embedding=provider,
        patterns=patterns,
    )
