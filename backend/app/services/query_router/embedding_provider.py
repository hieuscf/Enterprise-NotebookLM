# =============================================================================
# File: embedding_provider.py
# Module/Service: Query Router — Query Classifier (FR11)
# Layer: Adapter
# Purpose: EmbeddingProvider abstraction + default hashing / settings adapters.
# Responsibilities:
#   - Define EmbeddingProvider Protocol (NDArray output)
#   - Provide HashingNgramEmbeddingProvider (CI / no remote model)
#   - Provide SettingsEmbeddingProvider wrapping app.ai.embedding
# Dependencies:
#   - numpy, app.ai.embedding (settings adapter only)
# Public Exports:
#   - EmbeddingProvider, HashingNgramEmbeddingProvider, SettingsEmbeddingProvider
# Database/Table: N/A
# Related Modules: app.services.query_router.rule_classifier
# Important Notes: Classifier depends only on the Protocol — swap freely.
# =============================================================================

from __future__ import annotations

import hashlib
import re
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from app.ai.embedding import embed_texts_batch
from app.core.config import Settings

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Abstraction for dense text embeddings used by the classifier."""

    def embed(self, texts: list[str]) -> NDArray[np.float64]:
        """Embed ``texts`` into a ``(n, dim)`` float matrix.

        Args:
            texts: Input strings (already normalized recommended).

        Returns:
            Contiguous ``float64`` array of shape ``(len(texts), dimension)``.
        """
        ...


class HashingNgramEmbeddingProvider:
    """Local hashing-trick embeddings (word + char n-grams), no external model.

    Shared tokens produce overlapping features so few-shot centroids are
    meaningful in CI without SentenceTransformers / remote APIs.
    """

    def __init__(
        self,
        *,
        dimension: int = 256,
        ngram_min: int = 3,
        ngram_max: int = 5,
    ) -> None:
        if dimension < 8:
            raise ValueError("dimension must be >= 8")
        if ngram_min < 1 or ngram_max < ngram_min:
            raise ValueError("invalid n-gram range")
        self._dimension = dimension
        self._ngram_min = ngram_min
        self._ngram_max = ngram_max

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> NDArray[np.float64]:
        if not texts:
            return np.zeros((0, self._dimension), dtype=np.float64)
        rows = [self._embed_one(t) for t in texts]
        return np.vstack(rows)

    def _embed_one(self, text: str) -> NDArray[np.float64]:
        vec = np.zeros(self._dimension, dtype=np.float64)
        features = self._features(text or "")
        if not features:
            # Avoid zero vector (undefined cosine) — use a tiny deterministic bump.
            vec[0] = 1.0
            return vec
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self._dimension
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec /= norm
        return vec

    def _features(self, text: str) -> list[str]:
        compact = text.lower().strip()
        tokens = _TOKEN_RE.findall(compact)
        feats: list[str] = [f"w:{tok}" for tok in tokens]
        # Character n-grams over space-stripped text for VI diacritics / short queries.
        chars = re.sub(r"\s+", "", compact)
        if chars:
            for n in range(self._ngram_min, self._ngram_max + 1):
                if len(chars) < n:
                    continue
                for i in range(len(chars) - n + 1):
                    feats.append(f"c{n}:{chars[i : i + n]}")
        return feats


class SettingsEmbeddingProvider:
    """Adapter over ``app.ai.embedding.embed_texts_batch`` using ``Settings``."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def embed(self, texts: list[str]) -> NDArray[np.float64]:
        if not texts:
            return np.zeros((0, self._settings.embedding_dimension), dtype=np.float64)
        vectors = embed_texts_batch(
            texts,
            model_name=self._settings.embedding_model_name,
            dimension=self._settings.embedding_dimension,
            provider=self._settings.embedding_provider,
            api_key=self._settings.embedding_api_key,
            batch_size=self._settings.embedding_batch_size,
        )
        return np.asarray([v.values for v in vectors], dtype=np.float64)
