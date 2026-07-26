# =============================================================================
# File: embedding.py
# Module/Service: Pipeline Worker — Embedding ([AI])
# Layer: Service
# Purpose: Batch embedding for document chunks (local / OpenAI / Voyage) (FR2).
# Responsibilities:
#   - embed_texts_batch: provider dispatch with batching; return vectors
#   - Local hash fallback when no API key (Celery must not call Anthropic LLM)
# Dependencies:
#   - httpx (remote providers), hashlib (local)
# Public Exports:
#   - EmbeddingVector, embed_texts, embed_texts_batch
# Database/Table: embeddings (metadata only; vectors go to Qdrant)
# Related Modules: app.workers.stages.embedding, app.adapters.qdrant_store
# Important Notes: Voyage/OpenAI embedding APIs are allowed from Celery; Anthropic LLM is not.
# =============================================================================

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """One dense vector with provenance metadata."""

    values: list[float]
    model_name: str
    dimension: int


def embed_texts(
    texts: list[str],
    *,
    model_name: str,
    dimension: int,
) -> list[EmbeddingVector]:
    """Embed texts with the local hash provider (backward-compatible helper)."""
    return _embed_local_batch(texts, model_name=model_name, dimension=dimension)


def embed_texts_batch(
    texts: list[str],
    *,
    model_name: str,
    dimension: int,
    provider: str = "local",
    api_key: str | None = None,
    batch_size: int = 32,
    timeout_seconds: float = 60.0,
) -> list[EmbeddingVector]:
    """Embed ``texts`` in batches via the configured provider.

    Args:
        texts: Chunk contents in order.
        model_name: Model id (e.g. ``voyage-3``, ``text-embedding-3-large``).
        dimension: Expected output dimension (validated for remote APIs when possible).
        provider: ``local`` | ``openai`` | ``voyage``.
        api_key: Required for remote providers.
        batch_size: Max texts per API request.
        timeout_seconds: HTTP timeout per batch.

    Returns:
        One ``EmbeddingVector`` per input text (same order).
    """
    if not texts:
        return []
    batch_size = max(1, batch_size)
    provider_norm = (provider or "local").strip().lower()

    if provider_norm == "local" or not api_key:
        return _embed_local_batch(texts, model_name=model_name, dimension=dimension)

    out: list[EmbeddingVector] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        if provider_norm == "openai":
            out.extend(
                _embed_openai_batch(
                    batch,
                    model_name=model_name,
                    dimension=dimension,
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                )
            )
        elif provider_norm == "voyage":
            out.extend(
                _embed_voyage_batch(
                    batch,
                    model_name=model_name,
                    dimension=dimension,
                    api_key=api_key,
                    timeout_seconds=timeout_seconds,
                )
            )
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")
    return out


def _embed_local_batch(
    texts: list[str],
    *,
    model_name: str,
    dimension: int,
) -> list[EmbeddingVector]:
    return [_embed_one_local(t, model_name=model_name, dimension=dimension) for t in texts]


def _embed_one_local(text: str, *, model_name: str, dimension: int) -> EmbeddingVector:
    """Deterministic unit vector — no network (dev/CI / no API key)."""
    seed = hashlib.sha256(f"{model_name}:{text}".encode()).digest()
    values: list[float] = []
    counter = 0
    while len(values) < dimension:
        block = hashlib.sha256(seed + counter.to_bytes(4, "little")).digest()
        for i in range(0, len(block), 4):
            if len(values) >= dimension:
                break
            (unsigned,) = struct.unpack_from("!I", block, i)
            values.append((unsigned / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return EmbeddingVector(
        values=[v / norm for v in values],
        model_name=model_name,
        dimension=dimension,
    )


def _embed_openai_batch(
    texts: list[str],
    *,
    model_name: str,
    dimension: int,
    api_key: str,
    timeout_seconds: float,
) -> list[EmbeddingVector]:
    payload: dict[str, object] = {"model": model_name, "input": texts}
    # text-embedding-3-* supports dimensions truncation.
    if model_name.startswith("text-embedding-3"):
        payload["dimensions"] = dimension
    with httpx.Client(timeout=timeout_seconds) as client:
        resp = client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
    data_sorted = sorted(data, key=lambda row: row["index"])
    vectors: list[EmbeddingVector] = []
    for row in data_sorted:
        values = list(row["embedding"])
        if len(values) != dimension:
            raise ValueError(
                f"OpenAI embedding dimension mismatch: got {len(values)}, expected {dimension}"
            )
        vectors.append(EmbeddingVector(values=values, model_name=model_name, dimension=dimension))
    return vectors


def _embed_voyage_batch(
    texts: list[str],
    *,
    model_name: str,
    dimension: int,
    api_key: str,
    timeout_seconds: float,
) -> list[EmbeddingVector]:
    with httpx.Client(timeout=timeout_seconds) as client:
        resp = client.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model_name,
                "input": texts,
                "input_type": "document",
            },
        )
        resp.raise_for_status()
        data = resp.json()["data"]
    data_sorted = sorted(data, key=lambda row: row["index"])
    vectors: list[EmbeddingVector] = []
    for row in data_sorted:
        values = list(row["embedding"])
        # Voyage may return native dims; truncate/pad only if configured smaller.
        if len(values) > dimension:
            values = values[:dimension]
        if len(values) != dimension:
            raise ValueError(
                f"Voyage embedding dimension mismatch: got {len(values)}, expected {dimension}"
            )
        vectors.append(EmbeddingVector(values=values, model_name=model_name, dimension=dimension))
    return vectors
