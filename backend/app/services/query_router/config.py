# =============================================================================
# File: config.py
# Module/Service: Query Router — Query Classifier (FR11)
# Layer: Service
# Purpose: Threshold / path configuration for rule + embedding classification.
# Responsibilities:
#   - Hold confidence / margin thresholds (no magic numbers in classifier)
#   - Resolve examples directory and embedding dimension
# Dependencies:
#   - app.core.config.Settings (optional factory)
# Public Exports:
#   - ClassifierConfig, build_classifier_config, default_examples_dir
# Database/Table: N/A
# Related Modules: app.services.query_router.rule_classifier
# Important Notes: Never return cache_hit; thresholds must stay configurable.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import Settings, get_settings


def default_examples_dir() -> Path:
    """Package-local ``examples/`` directory (factoid.json / complex.json)."""
    return Path(__file__).resolve().parent / "examples"


@dataclass(frozen=True, slots=True)
class ClassifierConfig:
    """Immutable classifier settings (threshold, margin, embedding, paths)."""

    confidence_threshold: float
    margin_threshold: float
    embedding_dimension: int
    examples_dir: Path

    def __post_init__(self) -> None:
        if self.confidence_threshold < 0.0 or self.confidence_threshold > 1.0:
            raise ValueError("confidence_threshold must be in [0, 1]")
        if self.margin_threshold < 0.0 or self.margin_threshold > 1.0:
            raise ValueError("margin_threshold must be in [0, 1]")
        if self.embedding_dimension < 8:
            raise ValueError("embedding_dimension must be >= 8")


def build_classifier_config(settings: Settings | None = None) -> ClassifierConfig:
    """Build ``ClassifierConfig`` from application ``Settings``.

    Args:
        settings: Optional settings; defaults to ``get_settings()``.

    Returns:
        Frozen classifier configuration.
    """
    cfg = settings or get_settings()
    return ClassifierConfig(
        confidence_threshold=float(cfg.query_router_classifier_confidence_threshold),
        margin_threshold=float(cfg.query_router_classifier_margin_threshold),
        embedding_dimension=int(cfg.query_router_classifier_embedding_dimension),
        examples_dir=default_examples_dir(),
    )


@lru_cache
def get_classifier_config() -> ClassifierConfig:
    """Cached default classifier config from ``get_settings()``."""
    return build_classifier_config(get_settings())
