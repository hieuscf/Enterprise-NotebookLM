# =============================================================================
# File: embedding.py
# Module/Service: Pipeline Worker — Embedding ([AI])
# Layer: Service
# Purpose: Local deterministic embedding for chunk vectors (FR2).
# Responsibilities:
#   - Produce fixed-dimension float vectors; report model_name/dimension
# Dependencies:
#   - hashlib, math (no Anthropic — Celery must not call LLM Provider)
# Public Exports:
#   - EmbeddingVector, embed_texts
# Database/Table: embeddings (metadata only; vectors go to Qdrant)
# Related Modules: app.workers.pipeline (stage_embedding), app.adapters.qdrant_store
# Important Notes: Swap implementation later without changing worker contract.
# =============================================================================

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    values: list[float]
    model_name: str
    dimension: int


def embed_texts(
    texts: list[str],
    *,
    model_name: str,
    dimension: int,
) -> list[EmbeddingVector]:
    return [_embed_one(t, model_name=model_name, dimension=dimension) for t in texts]


def _embed_one(text: str, *, model_name: str, dimension: int) -> EmbeddingVector:
    """Hash-based unit vector — stable across runs, no external API.

    Good enough for wiring Qdrant + embeddings metadata in GĐ1; replace with
    sentence-transformers / voyage later without changing stage orchestration.
    """
    seed = hashlib.sha256(f"{model_name}:{text}".encode()).digest()
    values: list[float] = []
    counter = 0
    while len(values) < dimension:
        block = hashlib.sha256(seed + counter.to_bytes(4, "little")).digest()
        for i in range(0, len(block), 4):
            if len(values) >= dimension:
                break
            (unsigned,) = struct.unpack_from("!I", block, i)
            # Map to [-1, 1]
            values.append((unsigned / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1

    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    unit = [v / norm for v in values]
    return EmbeddingVector(values=unit, model_name=model_name, dimension=dimension)
