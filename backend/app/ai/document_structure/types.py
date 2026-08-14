# =============================================================================
# File: types.py
# Module/Service: Document Structure Extraction (FR8 / TASK-CMP-01)
# Layer: Service
# Purpose: Canonical in-memory representation of a document's hierarchical
#   structure (article / clause / appendix) for clause mapping & comparison.
# Responsibilities:
#   - Define StructuralUnitType, confidence labels, source spans, corpus inputs
#   - Provide DocumentStructure helpers (walk, canonical index) without I/O
# Dependencies:
#   - stdlib dataclasses / enum
# Public Exports:
#   - StructuralUnitType, ExtractionConfidence, SourceSpan, CorpusChunk,
#     CorpusLine, DetectedMarker, StructuralUnit, DocumentStructure,
#     DocumentCorpus, TYPE_LEVEL, canonical_key
# Database/Table: N/A (derived from document_chunks + layout_metadata)
# Related Modules: app.ai.document_structure.pipeline, extractor service
# Important Notes:
#   - Structure is derived from the FULL ingested corpus, never top-k retrieval.
#   - original text is stored as-is; number/type are normalized separately.
#   - No start/end offsets are invented when the pipeline does not provide them.
# =============================================================================

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


class StructuralUnitType(StrEnum):
    """Canonical structural unit kinds (legal + general documents)."""

    DOCUMENT = "DOCUMENT"
    CHAPTER = "CHAPTER"
    SECTION = "SECTION"
    ARTICLE = "ARTICLE"
    CLAUSE = "CLAUSE"
    SUB_CLAUSE = "SUB_CLAUSE"
    ITEM = "ITEM"
    APPENDIX = "APPENDIX"
    PARAGRAPH = "PARAGRAPH"
    OTHER = "OTHER"


class ExtractionConfidence(StrEnum):
    """Qualitative detection confidence — only set when detection actually ran."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# Hierarchy rank used to attach parent/child (lower = shallower).
TYPE_LEVEL: dict[StructuralUnitType, int] = {
    StructuralUnitType.DOCUMENT: 0,
    StructuralUnitType.CHAPTER: 1,
    StructuralUnitType.APPENDIX: 1,
    StructuralUnitType.SECTION: 2,
    StructuralUnitType.ARTICLE: 2,
    StructuralUnitType.CLAUSE: 3,
    StructuralUnitType.SUB_CLAUSE: 4,
    StructuralUnitType.ITEM: 5,
    StructuralUnitType.PARAGRAPH: 6,
    StructuralUnitType.OTHER: 6,
}

# Which child types may nest under a parent. ARTICLE is never nested under APPENDIX.
COMPATIBLE_CHILDREN: dict[StructuralUnitType, frozenset[StructuralUnitType]] = {
    StructuralUnitType.DOCUMENT: frozenset(
        {
            StructuralUnitType.CHAPTER,
            StructuralUnitType.APPENDIX,
            StructuralUnitType.SECTION,
            StructuralUnitType.ARTICLE,
            StructuralUnitType.CLAUSE,
            StructuralUnitType.SUB_CLAUSE,
            StructuralUnitType.ITEM,
            StructuralUnitType.PARAGRAPH,
            StructuralUnitType.OTHER,
        }
    ),
    StructuralUnitType.CHAPTER: frozenset(
        {
            StructuralUnitType.SECTION,
            StructuralUnitType.ARTICLE,
            StructuralUnitType.CLAUSE,
            StructuralUnitType.SUB_CLAUSE,
            StructuralUnitType.ITEM,
            StructuralUnitType.PARAGRAPH,
            StructuralUnitType.OTHER,
        }
    ),
    StructuralUnitType.APPENDIX: frozenset(
        {
            StructuralUnitType.SECTION,
            StructuralUnitType.CLAUSE,
            StructuralUnitType.SUB_CLAUSE,
            StructuralUnitType.ITEM,
            StructuralUnitType.PARAGRAPH,
            StructuralUnitType.OTHER,
        }
    ),
    StructuralUnitType.SECTION: frozenset(
        {
            StructuralUnitType.ARTICLE,
            StructuralUnitType.CLAUSE,
            StructuralUnitType.SUB_CLAUSE,
            StructuralUnitType.ITEM,
            StructuralUnitType.PARAGRAPH,
            StructuralUnitType.OTHER,
        }
    ),
    StructuralUnitType.ARTICLE: frozenset(
        {
            StructuralUnitType.CLAUSE,
            StructuralUnitType.SUB_CLAUSE,
            StructuralUnitType.ITEM,
            StructuralUnitType.PARAGRAPH,
            StructuralUnitType.SECTION,
            StructuralUnitType.OTHER,
        }
    ),
    StructuralUnitType.CLAUSE: frozenset(
        {
            StructuralUnitType.SUB_CLAUSE,
            StructuralUnitType.ITEM,
            StructuralUnitType.PARAGRAPH,
            StructuralUnitType.OTHER,
        }
    ),
    StructuralUnitType.SUB_CLAUSE: frozenset(
        {
            StructuralUnitType.ITEM,
            StructuralUnitType.PARAGRAPH,
            StructuralUnitType.OTHER,
        }
    ),
    StructuralUnitType.ITEM: frozenset(
        {StructuralUnitType.PARAGRAPH, StructuralUnitType.OTHER}
    ),
    StructuralUnitType.PARAGRAPH: frozenset(),
    StructuralUnitType.OTHER: frozenset({StructuralUnitType.PARAGRAPH}),
}

CONFIDENCE_SCORE: dict[ExtractionConfidence, float] = {
    ExtractionConfidence.HIGH: 0.98,
    ExtractionConfidence.MEDIUM: 0.72,
    ExtractionConfidence.LOW: 0.35,
}


def canonical_key(
    unit_type: StructuralUnitType | str,
    number: str | None,
) -> str | None:
    """Stable mapping key, e.g. ``ARTICLE:1`` / ``CLAUSE:1.2`` / ``APPENDIX:01``.

    Units without a number are omitted from the comparison index (they are not
    clause-mappable by number).
    """
    if not number:
        return None
    kind = unit_type.value if isinstance(unit_type, StructuralUnitType) else str(unit_type)
    return f"{kind}:{number}"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Evidence locator for a structural unit. Offsets are omitted unless known."""

    chunk_id: UUID | None = None
    page_number: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.chunk_id is not None:
            payload["chunk_id"] = str(self.chunk_id)
        if self.page_number is not None:
            payload["page_number"] = self.page_number
        if self.start_offset is not None:
            payload["start_offset"] = self.start_offset
        if self.end_offset is not None:
            payload["end_offset"] = self.end_offset
        return payload


@dataclass(frozen=True, slots=True)
class CorpusChunk:
    """One ingested chunk. Structure extraction reads ALL of these, not top-k."""

    chunk_id: UUID
    chunk_index: int
    content: str
    page_number: int | None = None
    layout_type: str | None = None
    heading_path: str | None = None
    section: str | None = None
    parent_chunk_id: UUID | None = None
    depth: int | None = None


@dataclass(frozen=True, slots=True)
class CorpusLine:
    """One original line in document order, bound to its source chunk/page."""

    text: str
    chunk_id: UUID | None
    chunk_index: int
    page_number: int | None
    line_in_chunk: int
    is_heading_chunk: bool = False
    skip_as_boilerplate: bool = False


@dataclass(frozen=True, slots=True)
class DetectedMarker:
    """A structural heading/numbering hit on a corpus line (original text intact)."""

    unit_type: StructuralUnitType
    number: str | None
    title: str
    raw_line: str
    confidence: ExtractionConfidence
    source: str
    line_index: int


@dataclass
class StructuralUnit:
    """One node in the normalized document structure tree."""

    id: str
    document_id: UUID
    type: StructuralUnitType
    number: str | None
    title: str
    text: str
    level: int
    parent_id: str | None
    order_index: int
    page_start: int | None = None
    page_end: int | None = None
    chunk_ids: list[UUID] = field(default_factory=list)
    source_spans: list[SourceSpan] = field(default_factory=list)
    children: list[StructuralUnit] = field(default_factory=list)
    confidence: float | None = None
    confidence_label: ExtractionConfidence | None = None
    original_heading: str | None = None
    detection_source: str | None = None

    def canonical_key(self) -> str | None:
        return canonical_key(self.type, self.number)

    def walk(self) -> Iterator[StructuralUnit]:
        yield self
        for child in self.children:
            yield from child.walk()

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "document_id": str(self.document_id),
            "type": self.type.value,
            "number": self.number,
            "title": self.title,
            "text": self.text,
            "level": self.level,
            "parent_id": self.parent_id,
            "order_index": self.order_index,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chunk_ids": [str(cid) for cid in self.chunk_ids],
            "source_spans": [span.as_dict() for span in self.source_spans],
            "children": [child.as_dict() for child in self.children],
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.confidence_label is not None:
            payload["confidence_label"] = self.confidence_label.value
        if self.original_heading is not None:
            payload["original_heading"] = self.original_heading
        if self.detection_source is not None:
            payload["detection_source"] = self.detection_source
        return payload


@dataclass
class DocumentStructure:
    """Normalized clause/section tree for one ingested document version."""

    document_id: UUID
    title: str
    metadata: dict[str, Any] = field(default_factory=dict)
    sections: list[StructuralUnit] = field(default_factory=list)
    version_id: UUID | None = None
    workspace_id: UUID | None = None
    root: StructuralUnit | None = None

    def walk(self) -> Iterator[StructuralUnit]:
        if self.root is not None:
            yield from self.root.walk()
            return
        for section in self.sections:
            yield from section.walk()

    def find(
        self,
        unit_type: StructuralUnitType,
        number: str,
    ) -> StructuralUnit | None:
        """Return the first unit with matching type+number (full tree, not top-k)."""
        wanted = canonical_key(unit_type, number)
        if wanted is None:
            return None
        for unit in self.walk():
            if unit.type is StructuralUnitType.DOCUMENT:
                continue
            if unit.canonical_key() == wanted:
                return unit
        return None

    def canonical_index(self) -> dict[str, StructuralUnit]:
        """Map ``TYPE:number`` → unit. First occurrence wins (document order)."""
        index: dict[str, StructuralUnit] = {}
        for unit in self.walk():
            if unit.type is StructuralUnitType.DOCUMENT:
                continue
            key = unit.canonical_key()
            if key and key not in index:
                index[key] = unit
        return index

    def canonical_keys(self) -> set[str]:
        return set(self.canonical_index())

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "title": self.title,
            "metadata": dict(self.metadata),
            "version_id": str(self.version_id) if self.version_id else None,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "sections": [unit.as_dict() for unit in self.sections],
        }


@dataclass(frozen=True, slots=True)
class DocumentCorpus:
    """Full ingested representation used as the sole extraction input."""

    document_id: UUID
    title: str
    chunks: list[CorpusChunk]
    layout_metadata: dict[str, Any] | None = None
    version_id: UUID | None = None
    workspace_id: UUID | None = None
    page_count: int | None = None
