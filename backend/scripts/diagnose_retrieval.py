# =============================================================================
# File: diagnose_retrieval.py
# Module/Service: Search Service / Hybrid Retrieval — Diagnostics (throwaway)
# Layer: Adapter
# Purpose: One-shot CLI to reproduce retrieval + context + answer for a fixed
#   set of test queries against a real workspace/document, without mutating
#   any persisted state (no message/session writes).
# Responsibilities:
#   - Run Vector/BM25/Graph individually + merged + reranked, dump diagnostics
#   - Run current PromptAnswerGenerator against the reranked result to capture
#     the actual answer produced by today's prompt/context assembly
# Dependencies:
#   - HybridRetrievalService plumbing (real adapters), PromptAnswerGenerator
# Public Exports: N/A (CLI script)
# Database/Table: read-only (documents, document_chunks via hydration)
# Related Modules: app.services.retrieval.*, app.services.chat.*
# Important Notes: Diagnostic only — do not import from application code.
# =============================================================================

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

from app.adapters.elasticsearch_bm25 import get_elasticsearch_bm25
from app.adapters.neo4j_graph import get_neo4j_graph
from app.adapters.qdrant_store import get_qdrant_store
from app.core.config import get_settings
from app.db.session import async_session_factory
from app.repositories.retrieval import RetrievalRepository
from app.services.chat.answer_generator import PromptAnswerGenerator
from app.services.chat.context_assembly import RetrievalRepositoryContextPort
from app.services.retrieval.bm25_search import Bm25Search
from app.services.retrieval.graph_search import GraphSearch
from app.services.retrieval.hybrid_retrieval_service import HybridRetrievalService, _merge_dedupe
from app.services.retrieval.query_expansion import classify_query_intent, expand_lexical_query
from app.services.retrieval.reranker import Reranker
from app.services.retrieval.schemas import RetrievalResult
from app.services.retrieval.vector_search import VectorSearch
from app.services.retrieval.confidence_engine import build_confidence_config, compute_confidence
from app.services.chat.complex_query_pipeline import _to_reranked

QUERIES = [
    "Tài liệu này trình bày kiến trúc hệ thống như thế nào?",
    "Nội dung chính của tài liệu",
    "Hợp đồng này quy định những nội dung gì?",
    "Ai là các bên trong tài liệu?",
    "Các nghĩa vụ chính của các bên là gì?",
    "Điều kiện/thời hạn/chấm dứt của hợp đồng là gì?",
]


def _trunc(s: str | None, n: int = 100) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s[:n] + ("…" if len(s) > n else "")


async def run_for_workspace(workspace_id: UUID, label: str) -> None:
    settings = get_settings()
    async with async_session_factory() as session:
        repo = RetrievalRepository(session)
        vector_search = VectorSearch(settings=settings, qdrant=get_qdrant_store(), repo=repo)
        bm25_search = Bm25Search(settings=settings, elasticsearch=get_elasticsearch_bm25(), repo=repo)
        graph_search = GraphSearch(settings=settings, neo4j=get_neo4j_graph(), repo=repo)
        reranker = Reranker(settings)
        hybrid = HybridRetrievalService(
            settings=settings,
            vector_search=vector_search,
            bm25_search=bm25_search,
            graph_search=graph_search,
            reranker=reranker,
        )
        answer_gen = PromptAnswerGenerator(
            settings, context_port=RetrievalRepositoryContextPort(repo)
        )

        print(f"\n{'=' * 100}\nWORKSPACE: {label} ({workspace_id})\n{'=' * 100}")

        for q in QUERIES:
            print(f"\n{'-' * 100}\nQUERY: {q}\n{'-' * 100}")
            intent = classify_query_intent(q)
            bm25_q = expand_lexical_query(q)
            print(f"query_intent={intent.value} bm25_expanded={_trunc(bm25_q, 140)}")
            per_source = settings.retrieval_per_source_top_k
            v = await vector_search.search(workspace_id, q, per_source)
            b = await bm25_search.search(workspace_id, bm25_q, per_source)
            g = await graph_search.search(workspace_id, q, per_source)
            print(f"vector={len(v)} bm25={len(b)} graph={len(g)}")

            merged = _merge_dedupe([*v, *b, *g])
            print(f"merged(candidate_count)={len(merged)}")

            capped = merged[: settings.retrieval_max_rerank_candidates]
            ranked = await reranker.rerank(q, capped)
            top_k = max(1, int(settings.retrieval_per_source_top_k))
            final = ranked[:top_k]
            for i, item in enumerate(final, start=1):
                item.rank = i

            unique_docs = {str(c.document_id) for c in final if c.document_id}
            unique_sections = {
                f"{c.document_id}:{c.section_title or c.section_index}" for c in final
            }
            print(
                f"reranked_count={len(ranked)} final_count={len(final)} "
                f"unique_documents={len(unique_docs)} unique_sections={len(unique_sections)}"
            )

            conf_cfg = build_confidence_config(settings)
            confidence = compute_confidence(_to_reranked(final), conf_cfg)
            print(
                f"confidence_score={confidence.confidence_score:.3f} "
                f"level={confidence.confidence_level.value} top_score={confidence.top_score:.3f} "
                f"spread={confidence.score_spread:.3f}"
            )

            print("\nFINAL CHUNKS (rank | method | score | doc_title | section | page | chars | text):")
            for c in final:
                print(
                    f"  #{c.rank:<2} {c.retrieval_method:<8} score={c.score:.3f} "
                    f"doc={_trunc(c.document_title, 28):<30} "
                    f"section={_trunc(c.section_title, 24):<26} "
                    f"page={c.page_number} sec_idx={c.section_index} "
                    f"len={len(c.text_snippet or '')} "
                    f"chunk_id={str(c.chunk_id)[:8]} "
                    f"text={_trunc(c.text_snippet, 90)}"
                )

            retrieval_result = RetrievalResult(
                items=final,
                latency_ms=0,
                sources_used=["vector", "bm25", "graph"],
                candidate_count=len(merged),
                reranked_count=len(ranked),
            )
            try:
                gen = await answer_gen.generate(
                    workspace_id=workspace_id,
                    query_text=q,
                    retrieval_result=retrieval_result,
                    confidence=confidence,
                )
                print(f"\nANSWER (model={gen.model_used}, citations={len(gen.citation_refs)}):")
                print(gen.answer)
                print(f"citation chunk_ids: {[str(c.chunk_id)[:8] for c in gen.citation_refs]}")
                if gen.expansion_items:
                    print(
                        f"context_expansion_added={len(gen.expansion_items)} "
                        f"chunk_ids={[str(c.chunk_id)[:8] for c in gen.expansion_items]}"
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"\nANSWER GENERATION FAILED: {type(exc).__name__}: {exc}")


async def main() -> None:
    targets = [
        (UUID("54b30d4b-e4e9-42f8-b8b0-6807c00418b9"), "LLM Hop dong uy quyen VINA"),
        (UUID("cd32dc3c-ff80-4367-8118-b670d0a59c23"), "NotebookLM Enterprise (architecture doc)"),
    ]
    for ws_id, label in targets:
        await run_for_workspace(ws_id, label)


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
