# =============================================================================
# File: graph_extraction.py
# Module/Service: Pipeline Worker — LightRAG Low-Level Graph ([AI])
# Layer: Service
# Purpose: Extract entities + relations from chunks without LLM (FR2).
# Responsibilities:
#   - Heuristic NER (proper nouns / acronyms) and co-occurrence relations
# Dependencies:
#   - re (local heuristics — Celery must not call Anthropic)
# Public Exports:
#   - ExtractedEntity, ExtractedRelation, extract_graph
# Database/Table: entities, entity_relations (persisted by worker)
# Related Modules: app.workers.pipeline (stage_graph_extraction), neo4j_graph
# Important Notes: LightRAG dual-level — this is Low-Level (Entities) branch.
# =============================================================================

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from app.ai.chunking import TextChunk

_PROPER_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")
_ACRONYM_RE = re.compile(r"\b([A-Z]{2,6})\b")
_STOP = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "And",
        "For",
        "With",
        "From",
        "Into",
        "About",
        "After",
        "Before",
        "While",
        "Where",
        "When",
        "What",
        "Which",
        "Who",
        "How",
        "Table",
        "Figure",
        "Section",
        "Chapter",
        "Page",
    }
)


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    name: str
    type: str
    description: str | None
    mentions: int


@dataclass(frozen=True, slots=True)
class ExtractedRelation:
    source_name: str
    target_name: str
    relation_type: str
    weight: float
    description: str | None = None


@dataclass(frozen=True, slots=True)
class GraphExtractionResult:
    entities: list[ExtractedEntity]
    relations: list[ExtractedRelation]


def extract_graph(chunks: list[TextChunk], *, max_entities: int = 40) -> GraphExtractionResult:
    mention_counter: Counter[str] = Counter()
    type_guess: dict[str, str] = {}
    cooccur: dict[tuple[str, str], int] = defaultdict(int)

    for chunk in chunks:
        names = _extract_names(chunk.content)
        for name in names:
            mention_counter[name] += 1
            type_guess.setdefault(name, _guess_type(name))
        unique = sorted(set(names))
        for i, a in enumerate(unique):
            for b in unique[i + 1 :]:
                key = (a, b) if a < b else (b, a)
                cooccur[key] += 1

    top = [name for name, _ in mention_counter.most_common(max_entities)]
    top_set = set(top)
    entities = [
        ExtractedEntity(
            name=name,
            type=type_guess.get(name, "CONCEPT"),
            description=f"Mentioned {mention_counter[name]} time(s) in document version",
            mentions=mention_counter[name],
        )
        for name in top
    ]

    relations: list[ExtractedRelation] = []
    for (a, b), weight in sorted(cooccur.items(), key=lambda x: -x[1]):
        if a in top_set and b in top_set and weight >= 1:
            relations.append(
                ExtractedRelation(
                    source_name=a,
                    target_name=b,
                    relation_type="CO_OCCURS_WITH",
                    weight=float(weight),
                    description="Co-occurrence within the same chunk",
                )
            )
        if len(relations) >= 80:
            break

    return GraphExtractionResult(entities=entities, relations=relations)


def _extract_names(text: str) -> list[str]:
    found: list[str] = []
    for match in _PROPER_RE.finditer(text):
        name = match.group(1).strip()
        if name not in _STOP and len(name) > 2:
            found.append(name)
    for match in _ACRONYM_RE.finditer(text):
        name = match.group(1)
        if name not in _STOP:
            found.append(name)
    return found


def _guess_type(name: str) -> str:
    if name.isupper() and 2 <= len(name) <= 6:
        return "ORG"
    if " " in name:
        return "ENTITY"
    return "CONCEPT"
