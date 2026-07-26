# =============================================================================
# File: topic_extraction.py
# Module/Service: Pipeline Worker — LightRAG High-Level Graph ([AI])
# Layer: Service
# Purpose: Hierarchical topic extraction from chunks (FR2 High-Level Retrieval).
# Responsibilities:
#   - Build parent/child topics (level) and map chunks via keyword affinity
# Dependencies:
#   - collections, re (non-LLM)
# Public Exports:
#   - ExtractedTopic, TopicExtractionResult, extract_topics
# Database/Table: topics, topic_chunks (persisted by worker)
# Related Modules: app.workers.pipeline (stage_graph_extraction / indexing)
# Important Notes: topics.parent_topic_id + level; Dual-level High-Level branch.
# =============================================================================

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from app.ai.chunking import TextChunk

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
_STOPWORDS = frozenset(
    """
    the and for that with this from are was were been being have has had
    not but into over such than then them they their what when where which
    while who will would could should about after before above below under
    between through during without within against among each other more most
    some any all also can may might must shall onto upon your yours our
    """.split()
)


@dataclass(frozen=True, slots=True)
class ExtractedTopic:
    name: str
    level: int
    summary: str | None
    parent_name: str | None
    chunk_indexes: list[int]


@dataclass(frozen=True, slots=True)
class TopicExtractionResult:
    topics: list[ExtractedTopic]


def extract_topics(
    chunks: list[TextChunk],
    *,
    max_root_topics: int = 5,
    max_child_per_root: int = 3,
) -> TopicExtractionResult:
    if not chunks:
        return TopicExtractionResult(topics=[])

    # Prefer explicit section titles when OCR provided them.
    section_groups: dict[str, list[int]] = {}
    for chunk in chunks:
        if chunk.section:
            section_groups.setdefault(chunk.section, []).append(chunk.chunk_index)

    topics: list[ExtractedTopic] = []
    if section_groups:
        root_name = "Document Themes"
        topics.append(
            ExtractedTopic(
                name=root_name,
                level=0,
                summary="Root topic derived from document sections",
                parent_name=None,
                chunk_indexes=[c.chunk_index for c in chunks],
            )
        )
        for section, idxs in list(section_groups.items())[:max_root_topics]:
            topics.append(
                ExtractedTopic(
                    name=section[:512],
                    level=1,
                    summary=f"Section covering {len(idxs)} chunk(s)",
                    parent_name=root_name,
                    chunk_indexes=idxs,
                )
            )
        return TopicExtractionResult(topics=topics)

    # Fallback: keyword affinity clusters.
    doc_terms = Counter()
    chunk_terms: list[Counter[str]] = []
    for chunk in chunks:
        terms = Counter(
            w.lower() for w in _WORD_RE.findall(chunk.content) if w.lower() not in _STOPWORDS
        )
        chunk_terms.append(terms)
        doc_terms.update(terms)

    roots = [t for t, _ in doc_terms.most_common(max_root_topics)]
    if not roots:
        return TopicExtractionResult(topics=[])

    topics.append(
        ExtractedTopic(
            name="Document Themes",
            level=0,
            summary="Root topic from keyword affinity",
            parent_name=None,
            chunk_indexes=[c.chunk_index for c in chunks],
        )
    )
    for root in roots:
        child_idxs = [
            chunks[i].chunk_index for i, terms in enumerate(chunk_terms) if terms.get(root, 0) > 0
        ]
        topics.append(
            ExtractedTopic(
                name=root.title(),
                level=1,
                summary=f"Keyword topic '{root}' ({len(child_idxs)} chunks)",
                parent_name="Document Themes",
                chunk_indexes=child_idxs or [chunks[0].chunk_index],
            )
        )
        # Optional level-2: related co-terms within those chunks.
        related: Counter[str] = Counter()
        for i, terms in enumerate(chunk_terms):
            if chunks[i].chunk_index in set(child_idxs):
                related.update(terms)
        related.pop(root, None)
        for child_term, _ in related.most_common(max_child_per_root):
            if child_term == root:
                continue
            topics.append(
                ExtractedTopic(
                    name=f"{root.title()} / {child_term.title()}",
                    level=2,
                    summary=f"Subtopic under {root}",
                    parent_name=root.title(),
                    chunk_indexes=child_idxs[:],
                )
            )
    return TopicExtractionResult(topics=topics)
