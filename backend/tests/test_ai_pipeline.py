# =============================================================================
# File: test_ai_pipeline.py
# Module/Service: LightRAG Pipeline stages ([AI])
# Layer: Service
# Purpose: Unit tests for OCR/chunk/embed/graph/topic without external infra.
# Responsibilities:
#   - Verify TXT OCR + chunking + embedding dim + entity/topic extraction
# Dependencies:
#   - pytest, app.ai.*
# Public Exports:
#   - N/A
# Database/Table: N/A
# Related Modules: app.workers.pipeline
# Important Notes: No Anthropic/MinIO/Qdrant — pure AI module contract tests.
# =============================================================================

from __future__ import annotations

from app.ai.chunking import run_chunking
from app.ai.embedding import embed_texts
from app.ai.graph_extraction import extract_graph
from app.ai.ocr import run_ocr_cleaning
from app.ai.topic_extraction import extract_topics
from app.models.enums import FileType


def test_ocr_chunk_embed_graph_topic_txt_flow() -> None:
    sample = (
        b"Enterprise NotebookLM Overview\n\n"
        b"Acme Corporation uses LightRAG for Dual-level Graph retrieval.\n"
        b"Vector Retrieval indexes Document Chunks in Qdrant.\n"
        b"Low-Level Entities connect Acme Corporation to LightRAG Core Engine.\n"
    )
    ocr = run_ocr_cleaning(file_type=FileType.txt, data=sample)
    assert ocr.page_count >= 1
    assert ocr.char_count > 0

    chunks = run_chunking(ocr.pages)
    assert len(chunks) >= 1
    assert chunks[0].token_count >= 1

    vectors = embed_texts(
        [c.content for c in chunks],
        model_name="local-hash-embedding-v1",
        dimension=384,
    )
    assert len(vectors) == len(chunks)
    assert len(vectors[0].values) == 384
    # Unit-ish vector
    norm = sum(v * v for v in vectors[0].values) ** 0.5
    assert abs(norm - 1.0) < 1e-6

    graph = extract_graph(chunks)
    assert isinstance(graph.entities, list)
    assert isinstance(graph.relations, list)

    topics = extract_topics(chunks)
    assert len(topics.topics) >= 1
    assert any(t.level == 0 for t in topics.topics)


def test_embedding_is_deterministic() -> None:
    a = embed_texts(["same text"], model_name="m", dimension=32)[0].values
    b = embed_texts(["same text"], model_name="m", dimension=32)[0].values
    assert a == b
