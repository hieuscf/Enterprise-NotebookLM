# =============================================================================
# File: semantic_text.py
# Module/Service: Semantic Clause Matching (FR8 / TASK-CMP-05)
# Layer: Service
# Purpose: Derived embedding text + process-local cache for clause vectors.
# Responsibilities:
#   - Build embedding_text from CMP-02 title/body/heading_path (never mutate)
#   - Cache key = hash(model_id + model_version + embedding_text)
# Dependencies:
#   - stdlib hashlib
#   - NormalizedUnit
# Public Exports:
#   - embedding_text, EmbeddingCache
# Database/Table: N/A (in-process cache only; Qdrant stays chunk-level)
# Related Modules: semantic_engine; query_router HashingNgramEmbeddingProvider
# Important Notes:
#   - Does not write original_text / normalized_body.
#   - Does not reuse vectors across model_name / model_version.
# =============================================================================

from __future__ import annotations

import hashlib
from collections.abc import Callable

from app.ai.document_structure.normalization import NormalizedUnit

EmbedFn = Callable[[list[str]], list[list[float]]]


def embedding_text(unit: NormalizedUnit, *, max_chars: int = 800) -> str:
    """Derived clause representation for embedding. Originals are not rewritten."""
    path = (unit.heading_path or "").strip()
    title = (unit.normalized_title or unit.folded_title or "").strip()
    body = (unit.normalized_body or unit.folded_body or "").strip()
    parts: list[str] = []
    if path and path.casefold() != title.casefold():
        parts.append(path)
    if title:
        parts.append(title)
    if body and body.casefold() != title.casefold():
        parts.append(body)
    text = " | ".join(parts) or (unit.identity_key or unit.source_id)
    if len(text) > max_chars:
        return text[:max_chars]
    return text


class EmbeddingCache:
    """Process-local vectors keyed by model + version + embedding_text hash."""

    def __init__(self, *, model_name: str, model_version: str) -> None:
        self.model_name = model_name
        self.model_version = model_version
        self._store: dict[str, list[float]] = {}
        self.hits = 0
        self.misses = 0

    def cache_key(self, text: str) -> str:
        payload = f"{self.model_name}|{self.model_version}|{text}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def compatible(self, model_name: str, model_version: str) -> bool:
        return self.model_name == model_name and self.model_version == model_version

    def get_or_embed(self, texts: list[str], embed_fn: EmbedFn) -> list[list[float] | None]:
        """Return cached vectors; embed only cache misses in one batch."""
        keys = [self.cache_key(text) for text in texts]
        missing_idx = [i for i, key in enumerate(keys) if key not in self._store]
        self.hits += len(texts) - len(missing_idx)
        self.misses += len(missing_idx)
        if missing_idx:
            batch = [texts[i] for i in missing_idx]
            vectors = embed_fn(batch)
            if len(vectors) != len(batch):
                raise ValueError("embed_fn length mismatch")
            for index, vector in zip(missing_idx, vectors, strict=True):
                self._store[keys[index]] = list(vector)
        return [list(self._store[key]) for key in keys]
