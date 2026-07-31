# =============================================================================
# File: reranker.py
# Module/Service: Search Service / Re-ranking Layer
# Layer: Service
# Purpose: Cross-encoder (non-LLM) re-ranking of Hybrid Retrieval candidates (FR3).
# Responsibilities:
#   - Score (query, text_snippet) pairs; set score + rank; sort descending
#   - heuristic backend for CI/local; optional sentence-transformers cross_encoder
# Dependencies:
#   - app.core.config.Settings; optional sentence_transformers
# Public Exports:
#   - Reranker
# Database/Table: N/A
# Related Modules: HybridRetrievalService, Confidence Engine (later)
# Important Notes: Never calls Anthropic/LLM. Does not mutate text_snippet.
# =============================================================================

from __future__ import annotations

import asyncio
import math
import re
from collections.abc import Sequence

from app.core.config import Settings
from app.core.logging import get_logger
from app.services.retrieval.schemas import RetrievalCandidate

logger = get_logger(__name__)

_TOKEN_RE = re.compile(
    r"[a-z0-9àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]+",
    re.I,
)


class Reranker:
    """Cross-encoder / heuristic re-ranker (0 LLM)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._model = None
        self._model_load_attempted = False

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
    ) -> list[RetrievalCandidate]:
        """Re-rank candidates by relevance to ``query``.

        Args:
            query: User query text.
            candidates: Merged / deduplicated candidates (pre-truncated).

        Returns:
            Same candidates with ``score`` and ``rank`` set, sorted by score desc.
            ``retrieval_method`` becomes ``rerank``; original methods kept in
            ``source_methods``.
        """
        if not candidates:
            return []

        backend = (self._settings.reranker_backend or "heuristic").strip().lower()
        if backend == "cross_encoder":
            scores = await asyncio.to_thread(self._cross_encoder_scores, query, candidates)
        else:
            scores = self._heuristic_scores(query, candidates)

        ranked: list[RetrievalCandidate] = []
        for cand, score in zip(candidates, scores, strict=True):
            methods = list(cand.source_methods) or [cand.retrieval_method]
            ranked.append(
                RetrievalCandidate(
                    workspace_id=cand.workspace_id,
                    text_snippet=cand.text_snippet,
                    retrieval_method="rerank",
                    raw_score=cand.raw_score,
                    document_id=cand.document_id,
                    chunk_id=cand.chunk_id,
                    entity_id=cand.entity_id,
                    score=float(score),
                    rank=None,
                    source_methods=methods,
                )
            )
        ranked.sort(key=lambda c: c.score if c.score is not None else 0.0, reverse=True)
        for i, cand in enumerate(ranked, start=1):
            cand.rank = i
        return ranked

    def _heuristic_scores(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
    ) -> list[float]:
        """Token-overlap + raw_score blend — deterministic, no model download."""
        q_tokens = set(_TOKEN_RE.findall(query.lower()))
        scores: list[float] = []
        for cand in candidates:
            text = (cand.text_snippet or "").lower()
            t_tokens = set(_TOKEN_RE.findall(text))
            if not q_tokens:
                overlap = 0.0
            else:
                overlap = len(q_tokens & t_tokens) / len(q_tokens)
            # Softmax-ish blend with raw retrieval score (normalized loosely).
            raw = max(0.0, float(cand.raw_score))
            raw_norm = raw / (1.0 + raw)
            scores.append(0.7 * overlap + 0.3 * raw_norm)
        return scores

    def _cross_encoder_scores(
        self,
        query: str,
        candidates: Sequence[RetrievalCandidate],
    ) -> list[float]:
        """Score with sentence-transformers CrossEncoder; fall back to heuristic."""
        model = self._ensure_cross_encoder()
        if model is None:
            logger.warning(
                "reranker_cross_encoder_unavailable_fallback_heuristic",
                model=self._settings.reranker_model_name,
            )
            return self._heuristic_scores(query, candidates)
        pairs = [(query, c.text_snippet or "") for c in candidates]
        raw_scores = model.predict(pairs)
        # Convert to plain floats; CrossEncoder may return numpy array.
        return [float(s) for s in raw_scores]

    def _ensure_cross_encoder(self):  # noqa: ANN202 — optional third-party type
        if self._model is not None:
            return self._model
        if self._model_load_attempted:
            return None
        self._model_load_attempted = True
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("sentence_transformers_not_installed")
            return None
        try:
            self._model = CrossEncoder(self._settings.reranker_model_name)
            return self._model
        except Exception as exc:  # noqa: BLE001 — model load is best-effort
            logger.warning("reranker_model_load_failed", error=str(exc))
            return None


def softmax(values: Sequence[float]) -> list[float]:
    """Numerically stable softmax (helper for tests / score inspection)."""
    if not values:
        return []
    m = max(values)
    exps = [math.exp(v - m) for v in values]
    total = sum(exps) or 1.0
    return [e / total for e in exps]
