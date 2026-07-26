# =============================================================================
# File: lightrag_extraction.py
# Module/Service: LightRAG Core Engine — Dual-level Graph ([AI])
# Layer: Service
# Purpose: Entity/relation + hierarchical topic extraction for ingestion (FR2 Step 5).
# Responsibilities:
#   - LLM (Haiku) structured extraction when API key present — COSTS MONEY
#   - Heuristic fallback (no LLM) for local/CI without Anthropic
# Dependencies:
#   - app.adapters.anthropic_client, app.ai.graph_extraction, topic_extraction
# Public Exports:
#   - LightRAGExtractionResult, extract_lightrag_knowledge
# Database/Table: entities, entity_relations, topics, topic_chunks (persisted by stage)
# Related Modules: app.workers.stages.graph_extraction
# Important Notes:
#   - Sole ingestion stage that may call Anthropic chat/completions (Haiku).
#   - Low-Level = entities/relations; High-Level = hierarchical topics.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adapters.anthropic_client import extract_structured_json
from app.ai.chunking import TextChunk
from app.ai.graph_extraction import (
    ExtractedEntity,
    ExtractedRelation,
    GraphExtractionResult,
    extract_graph,
)
from app.ai.topic_extraction import ExtractedTopic, TopicExtractionResult, extract_topics
from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class LightRAGExtractionResult:
    """Combined Low-Level + High-Level extraction for one document version."""

    entities: list[ExtractedEntity]
    relations: list[ExtractedRelation]
    topics: list[ExtractedTopic]
    llm_used: bool
    model_used: str | None
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


_SYSTEM_PROMPT = """You are a knowledge-graph extractor for an enterprise RAG system (LightRAG).
Return ONLY a JSON object (no markdown) with this schema:
{
  "entities": [{"name": string, "type": string, "description": string}],
  "relations": [{"source": string, "target": string, "relation_type": string, "description": string, "weight": number}],
  "topics": [
    {
      "name": string,
      "level": number,
      "summary": string,
      "parent_name": string|null,
      "chunk_indexes": number[]
    }
  ]
}
Rules:
- Entities: people, orgs, products, locations, concepts mentioned in the chunks.
- Relations: only between extracted entity names; weight in [0,1].
- Topics: hierarchical. level 0 = root theme(s), level 1+ = children with parent_name.
- chunk_indexes must reference the provided chunk_index integers.
- Prefer precision over recall; do not invent facts not supported by the text.
"""


def extract_lightrag_knowledge(
    chunks: list[TextChunk],
    *,
    settings: Settings,
) -> LightRAGExtractionResult:
    """Extract entities/relations/topics via LLM (Haiku) or heuristic fallback.

    Args:
        chunks: Chunks for the document version (already persisted).
        settings: App settings (API key, model, max chars).

    Returns:
        Combined extraction result with cost metadata.
    """
    if not chunks:
        return LightRAGExtractionResult(
            entities=[],
            relations=[],
            topics=[],
            llm_used=False,
            model_used=None,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
        )

    api_key = (settings.anthropic_api_key or "").strip()
    use_llm = bool(api_key) and settings.graph_llm_enabled

    if not use_llm:
        return _heuristic_extract(chunks)

    user_payload = _format_chunks_for_prompt(
        chunks,
        max_chars=settings.graph_llm_max_input_chars,
    )
    try:
        result = extract_structured_json(
            system=_SYSTEM_PROMPT,
            user=user_payload,
            model=settings.graph_llm_model,
            api_key=api_key,
            api_base=settings.anthropic_api_base,
            max_tokens=settings.graph_llm_max_tokens,
        )
        entities, relations, topics = _parse_llm_payload(result.data, chunks)
        return LightRAGExtractionResult(
            entities=entities,
            relations=relations,
            topics=topics,
            llm_used=True,
            model_used=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            estimated_cost_usd=result.estimated_cost_usd,
        )
    except Exception:
        # Fail soft to heuristic so ingestion can complete when LLM is flaky;
        # stage may still choose to surface TransientPipelineError if desired.
        fallback = _heuristic_extract(chunks)
        return LightRAGExtractionResult(
            entities=fallback.entities,
            relations=fallback.relations,
            topics=fallback.topics,
            llm_used=False,
            model_used=None,
            input_tokens=0,
            output_tokens=0,
            estimated_cost_usd=0.0,
        )


def _heuristic_extract(chunks: list[TextChunk]) -> LightRAGExtractionResult:
    graph: GraphExtractionResult = extract_graph(chunks)
    topics: TopicExtractionResult = extract_topics(chunks)
    return LightRAGExtractionResult(
        entities=graph.entities,
        relations=graph.relations,
        topics=topics.topics,
        llm_used=False,
        model_used=None,
        input_tokens=0,
        output_tokens=0,
        estimated_cost_usd=0.0,
    )


def _format_chunks_for_prompt(chunks: list[TextChunk], *, max_chars: int) -> str:
    lines: list[str] = [
        "Extract knowledge graph + hierarchical topics from these chunks.",
        "Each block starts with [chunk_index=N]:",
        "",
    ]
    used = 0
    for chunk in chunks:
        block = (
            f"[chunk_index={chunk.chunk_index} page={chunk.page_number} "
            f"section={chunk.section}]\n{chunk.content}\n"
        )
        if used + len(block) > max_chars:
            break
        lines.append(block)
        used += len(block)
    return "\n".join(lines)


def _parse_llm_payload(
    data: dict[str, Any],
    chunks: list[TextChunk],
) -> tuple[list[ExtractedEntity], list[ExtractedRelation], list[ExtractedTopic]]:
    valid_indexes = {c.chunk_index for c in chunks}
    entities: list[ExtractedEntity] = []
    seen_names: set[str] = set()
    for row in data.get("entities") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        entities.append(
            ExtractedEntity(
                name=name[:512],
                type=str(row.get("type") or "CONCEPT")[:128],
                description=(str(row["description"])[:2000] if row.get("description") else None),
                mentions=1,
            )
        )

    name_set = {e.name for e in entities}
    relations: list[ExtractedRelation] = []
    for row in data.get("relations") or []:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").strip()
        target = str(row.get("target") or "").strip()
        if not source or not target or source not in name_set or target not in name_set:
            continue
        if source == target:
            continue
        weight_raw = row.get("weight", 1.0)
        try:
            weight = float(weight_raw)
        except (TypeError, ValueError):
            weight = 1.0
        relations.append(
            ExtractedRelation(
                source_name=source,
                target_name=target,
                relation_type=str(row.get("relation_type") or "RELATED_TO")[:128],
                weight=max(0.0, min(1.0, weight)),
                description=(
                    str(row["description"])[:2000] if row.get("description") else None
                ),
            )
        )

    topics: list[ExtractedTopic] = []
    for row in data.get("topics") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        try:
            level = int(row.get("level", 0))
        except (TypeError, ValueError):
            level = 0
        parent_name = row.get("parent_name")
        parent = str(parent_name).strip() if parent_name else None
        raw_idxs = row.get("chunk_indexes") or []
        chunk_indexes = sorted(
            {
                int(i)
                for i in raw_idxs
                if str(i).lstrip("-").isdigit() and int(i) in valid_indexes
            }
        )
        if not chunk_indexes:
            chunk_indexes = [chunks[0].chunk_index]
        topics.append(
            ExtractedTopic(
                name=name[:512],
                level=max(0, level),
                summary=(str(row["summary"])[:4000] if row.get("summary") else None),
                parent_name=parent,
                chunk_indexes=chunk_indexes,
            )
        )

    if not topics:
        # Ensure High-Level branch always has at least heuristic topics.
        topics = extract_topics(chunks).topics

    return entities, relations, topics
