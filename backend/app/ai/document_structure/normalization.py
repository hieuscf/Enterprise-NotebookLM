# =============================================================================
# File: normalization.py
# Module/Service: Clause Normalization (FR8 / TASK-CMP-02)
# Layer: Service
# Purpose: Deterministic per-document normalization of structural units so
#   later mapping/comparison can use a single identity representation.
# Responsibilities:
#   - Canonical number/type, identity_key, qualified_key, number_path
#   - Normalized title/body + OCR-folded forms (original text never rewritten)
#   - Language aliases (Điều ≡ Article, Khoản ≡ Clause, Phụ lục ≡ Appendix)
# Dependencies:
#   - app.ai.document_structure.types, patterns
#   - app.ai.hierarchical_chunking.section_parser.normalize_heading_text
# Public Exports:
#   - NormalizedUnit, NormalizedDocumentStructure, normalize_structure,
#     normalize_title, normalize_body, build_aliases, identity_key_for
# Database/Table: N/A (derived in-memory from DocumentStructure)
# Related Modules: ClauseNormalizer service; TASK-CMP-03 mapping (not this file)
# Important Notes:
#   - Does NOT map V1↔V2 or compare clause text.
#   - Does NOT call LLM, embedding, or retrieval.
#   - Idempotent: same DocumentStructure → same identity keys / aliases.
# =============================================================================

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.ai.document_structure.patterns import fold_ocr_text, normalize_unit_number
from app.ai.document_structure.types import (
    DocumentStructure,
    ExtractionConfidence,
    SourceSpan,
    StructuralUnit,
    StructuralUnitType,
    canonical_key,
)
from app.ai.hierarchical_chunking.section_parser import (
    heading_number_parent,
    normalize_heading_text,
)

_SPACE_RE = re.compile(r"\s+", re.UNICODE)
_SOFT_HYPHEN_RE = re.compile(r"[\u00ad\u200b\u200c\u200d\ufeff]")
_NUMBER_PREFIX_RE = re.compile(
    r"^(?:#{1,6}\s+)?(?:điều|dieu|article|art\.?|khoản|khoan|clause|"
    r"phụ\s*lục|phu\s*luc|appendix|annex|chương|chuong|chapter|"
    r"mục|muc|section|điểm|diem)?\s*"
    r"(?P<number>\d+(?:\.\d+)*|[a-z]|[ivx]+)?\s*[:.\-—–)]*\s*",
    re.IGNORECASE | re.UNICODE,
)

DISPLAY_LABEL: dict[StructuralUnitType, str] = {
    StructuralUnitType.DOCUMENT: "Tài liệu",
    StructuralUnitType.CHAPTER: "Chương",
    StructuralUnitType.SECTION: "Mục",
    StructuralUnitType.ARTICLE: "Điều",
    StructuralUnitType.CLAUSE: "Khoản",
    StructuralUnitType.SUB_CLAUSE: "Khoản",
    StructuralUnitType.ITEM: "Điểm",
    StructuralUnitType.APPENDIX: "Phụ lục",
    StructuralUnitType.PARAGRAPH: "Đoạn",
    StructuralUnitType.OTHER: "Khác",
}

TYPE_ALIAS_LABELS: dict[StructuralUnitType, tuple[str, ...]] = {
    StructuralUnitType.ARTICLE: ("điều", "dieu", "article", "art"),
    StructuralUnitType.CLAUSE: ("khoản", "khoan", "clause", "điều", "dieu", "article"),
    StructuralUnitType.SUB_CLAUSE: ("khoản", "clause", "điểm", "diem"),
    StructuralUnitType.ITEM: ("điểm", "diem", "item"),
    StructuralUnitType.APPENDIX: ("phụ lục", "phu luc", "appendix", "annex", "schedule"),
    StructuralUnitType.CHAPTER: ("chương", "chuong", "chapter"),
    StructuralUnitType.SECTION: ("mục", "muc", "section", "phần", "phan"),
}

_NUMBERED_TYPES = frozenset(
    {
        StructuralUnitType.CHAPTER,
        StructuralUnitType.SECTION,
        StructuralUnitType.ARTICLE,
        StructuralUnitType.CLAUSE,
        StructuralUnitType.SUB_CLAUSE,
        StructuralUnitType.ITEM,
        StructuralUnitType.APPENDIX,
    }
)


@dataclass
class NormalizedUnit:
    """One structural unit with canonical identity fields. Original text intact."""

    source_id: str
    document_id: UUID
    type: StructuralUnitType
    canonical_number: str | None
    identity_key: str | None
    qualified_key: str | None
    number_path: tuple[str, ...]
    parent_identity_key: str | None
    original_title: str
    original_text: str
    original_heading: str | None
    normalized_title: str
    folded_title: str
    normalized_body: str
    folded_body: str
    aliases: tuple[str, ...]
    heading_path: str
    order_index: int
    level: int
    page_start: int | None = None
    page_end: int | None = None
    chunk_ids: tuple[UUID, ...] = ()
    source_spans: tuple[SourceSpan, ...] = ()
    children: list[NormalizedUnit] = field(default_factory=list)
    confidence: float | None = None
    confidence_label: ExtractionConfidence | None = None

    def walk(self) -> Iterator[NormalizedUnit]:
        yield self
        for child in self.children:
            yield from child.walk()

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "document_id": str(self.document_id),
            "type": self.type.value,
            "canonical_number": self.canonical_number,
            "identity_key": self.identity_key,
            "qualified_key": self.qualified_key,
            "number_path": list(self.number_path),
            "parent_identity_key": self.parent_identity_key,
            "original_title": self.original_title,
            "original_text": self.original_text,
            "original_heading": self.original_heading,
            "normalized_title": self.normalized_title,
            "folded_title": self.folded_title,
            "normalized_body": self.normalized_body,
            "folded_body": self.folded_body,
            "aliases": list(self.aliases),
            "heading_path": self.heading_path,
            "order_index": self.order_index,
            "level": self.level,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "chunk_ids": [str(cid) for cid in self.chunk_ids],
            "source_spans": [span.as_dict() for span in self.source_spans],
            "children": [child.as_dict() for child in self.children],
            "confidence": self.confidence,
            "confidence_label": (
                self.confidence_label.value if self.confidence_label else None
            ),
        }


@dataclass
class NormalizedDocumentStructure:
    """Per-document normalized tree. Not a V1↔V2 mapping."""

    document_id: UUID
    title: str
    sections: list[NormalizedUnit] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    version_id: UUID | None = None
    workspace_id: UUID | None = None
    root: NormalizedUnit | None = None

    def walk(self) -> Iterator[NormalizedUnit]:
        if self.root is not None:
            yield from self.root.walk()
            return
        for section in self.sections:
            yield from section.walk()

    def identity_index(self) -> dict[str, NormalizedUnit]:
        """``CLAUSE:1.2`` → unit. First occurrence in document order wins."""
        index: dict[str, NormalizedUnit] = {}
        for unit in self.walk():
            if unit.type is StructuralUnitType.DOCUMENT:
                continue
            if unit.identity_key and unit.identity_key not in index:
                index[unit.identity_key] = unit
        return index

    def identity_keys(self) -> set[str]:
        return set(self.identity_index())

    def find(
        self,
        unit_type: StructuralUnitType,
        number: str,
    ) -> NormalizedUnit | None:
        key = identity_key_for(unit_type, number)
        if key is None:
            return None
        return self.identity_index().get(key)

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "title": self.title,
            "metadata": dict(self.metadata),
            "version_id": str(self.version_id) if self.version_id else None,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "sections": [unit.as_dict() for unit in self.sections],
        }


def identity_key_for(
    unit_type: StructuralUnitType,
    number: str | None,
) -> str | None:
    """Stable identity used later by mapping — type+canonical number only."""
    if unit_type is StructuralUnitType.DOCUMENT:
        return None
    if unit_type not in _NUMBERED_TYPES:
        return None
    canonical = normalize_unit_number(number, unit_type) if number else None
    return canonical_key(unit_type, canonical)


def normalize_title(title: str) -> str:
    """Casefold + punctuation strip for titles. Does not rewrite ``original_title``."""
    cleaned = _SOFT_HYPHEN_RE.sub("", title or "")
    return normalize_heading_text(cleaned)


def normalize_body(text: str, *, heading: str | None = None) -> str:
    """Whitespace-normalized body with heading/numbering prefix removed.

    When the unit's exclusive span is a single heading line (typical for
    short clauses like ``1.2. Nội dung...``), the heading is not dropped
    wholesale — only the numbering prefix is stripped so the body remains.
    """
    raw = text or ""
    body = _strip_heading_line(raw, heading)
    if not body.strip():
        body = raw
    body = _strip_numbering_prefix(body)
    body = _SOFT_HYPHEN_RE.sub("", body)
    body = unicodedata.normalize("NFKC", body)
    body = _SPACE_RE.sub(" ", body).replace("\n", " ")
    return body.strip().casefold()


def build_aliases(
    unit_type: StructuralUnitType,
    number: str | None,
    *,
    parent_number: str | None = None,
    title: str | None = None,
) -> tuple[str, ...]:
    """Language-agnostic aliases for one numbered unit. Empty if unnumbered."""
    canonical = normalize_unit_number(number, unit_type) if number else None
    if not canonical:
        return ()
    aliases: set[str] = {_alias_form(canonical)}
    for label in TYPE_ALIAS_LABELS.get(unit_type, ()):
        aliases.add(_alias_form(f"{label} {canonical}"))
    if (
        unit_type in {StructuralUnitType.CLAUSE, StructuralUnitType.SUB_CLAUSE}
        and parent_number
        and canonical.startswith(f"{parent_number}.")
    ):
        rest = canonical[len(parent_number) + 1 :]
        aliases.add(_alias_form(f"điều {parent_number} khoản {rest}"))
        aliases.add(_alias_form(f"dieu {parent_number} khoan {rest}"))
        aliases.add(_alias_form(f"article {parent_number} clause {rest}"))
        aliases.add(_alias_form(f"điều {canonical}"))
        aliases.add(_alias_form(f"article {canonical}"))
    if unit_type is StructuralUnitType.APPENDIX:
        stripped = normalize_unit_number(canonical, StructuralUnitType.ARTICLE)
        if stripped and stripped != canonical:
            aliases.add(_alias_form(f"phụ lục {stripped}"))
            aliases.add(_alias_form(f"appendix {stripped}"))
    folded = {_alias_form(fold_ocr_text(item)) for item in list(aliases)}
    aliases.update(folded)
    title_norm = normalize_title(title or "")
    if title_norm:
        aliases.add(title_norm)
        aliases.add(_alias_form(fold_ocr_text(title_norm)))
    aliases.discard("")
    return tuple(sorted(aliases))


def normalize_structure(structure: DocumentStructure) -> NormalizedDocumentStructure:
    """Convert one extracted tree into canonical units. No cross-document logic."""
    if structure.root is not None:
        norm_root = _convert_unit(structure.root, parent=None, parent_numbers=())
        sections = list(norm_root.children)
    else:
        norm_root = None
        sections = [
            _convert_unit(section, parent=None, parent_numbers=())
            for section in structure.sections
        ]

    units = list(norm_root.walk()) if norm_root is not None else [
        u for section in sections for u in section.walk()
    ]
    numbered = [
        u
        for u in units
        if u.type is not StructuralUnitType.DOCUMENT and u.identity_key
    ]
    metadata = dict(structure.metadata)
    metadata.update(
        {
            "units_normalized": max(0, len(units) - (1 if norm_root is not None else 0)),
            "articles_normalized": sum(
                1 for u in numbered if u.type is StructuralUnitType.ARTICLE
            ),
            "clauses_normalized": sum(
                1
                for u in numbered
                if u.type in {StructuralUnitType.CLAUSE, StructuralUnitType.SUB_CLAUSE}
            ),
            "appendices_normalized": sum(
                1 for u in numbered if u.type is StructuralUnitType.APPENDIX
            ),
            "units_without_number": sum(
                1
                for u in units
                if u.type not in {StructuralUnitType.DOCUMENT} and not u.identity_key
            ),
            "normalization_llm_calls": 0,
        }
    )
    return NormalizedDocumentStructure(
        document_id=structure.document_id,
        title=structure.title,
        sections=sections,
        metadata=metadata,
        version_id=structure.version_id,
        workspace_id=structure.workspace_id,
        root=norm_root,
    )


def _convert_unit(
    unit: StructuralUnit,
    *,
    parent: NormalizedUnit | None,
    parent_numbers: tuple[str, ...],
) -> NormalizedUnit:
    canonical = (
        normalize_unit_number(unit.number, unit.type) if unit.number else None
    )
    identity = identity_key_for(unit.type, canonical)
    parent_number = parent.canonical_number if parent is not None else None
    if parent is not None and parent.type is StructuralUnitType.DOCUMENT:
        parent_number = heading_number_parent(canonical) or parent_number
    elif canonical and heading_number_parent(canonical):
        parent_number = heading_number_parent(canonical) or parent_number

    number_path = parent_numbers + ((canonical,) if canonical else ())
    parent_identity = (
        parent.identity_key
        if parent is not None and parent.type is not StructuralUnitType.DOCUMENT
        else None
    )
    if identity and parent is not None and parent.qualified_key:
        qualified = f"{parent.qualified_key}/{identity}"
    else:
        qualified = identity

    heading_path = _heading_path(parent, unit.type, canonical)
    original_title = unit.title or ""
    original_text = unit.text or ""
    original_heading = unit.original_heading
    title_norm = normalize_title(original_title)
    body_norm = normalize_body(original_text, heading=original_heading)
    aliases = build_aliases(
        unit.type,
        canonical,
        parent_number=parent_number,
        title=original_title,
    )

    converted = NormalizedUnit(
        source_id=unit.id,
        document_id=unit.document_id,
        type=unit.type,
        canonical_number=canonical,
        identity_key=identity,
        qualified_key=qualified,
        number_path=number_path,
        parent_identity_key=parent_identity,
        original_title=original_title,
        original_text=original_text,
        original_heading=original_heading,
        normalized_title=title_norm,
        folded_title=_alias_form(fold_ocr_text(title_norm)),
        normalized_body=body_norm,
        folded_body=_alias_form(fold_ocr_text(body_norm)),
        aliases=aliases,
        heading_path=heading_path,
        order_index=unit.order_index,
        level=unit.level,
        page_start=unit.page_start,
        page_end=unit.page_end,
        chunk_ids=tuple(unit.chunk_ids),
        source_spans=tuple(unit.source_spans),
        confidence=unit.confidence,
        confidence_label=unit.confidence_label,
    )
    converted.children = [
        _convert_unit(
            child,
            parent=converted,
            parent_numbers=number_path,
        )
        for child in unit.children
    ]
    return converted


def _heading_path(
    parent: NormalizedUnit | None,
    unit_type: StructuralUnitType,
    number: str | None,
) -> str:
    label = DISPLAY_LABEL.get(unit_type, unit_type.value)
    self_part = f"{label} {number}".strip() if number else label
    if parent is None or parent.type is StructuralUnitType.DOCUMENT or not parent.heading_path:
        return self_part if unit_type is not StructuralUnitType.DOCUMENT else label
    if unit_type is StructuralUnitType.DOCUMENT:
        return label
    return f"{parent.heading_path} > {self_part}"


def _strip_heading_line(text: str, heading: str | None) -> str:
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    heading_cmp = (heading or "").strip()
    if heading_cmp and lines and lines[0].strip() == heading_cmp:
        return "\n".join(lines[1:]).strip()
    return text.strip()


def _strip_numbering_prefix(text: str) -> str:
    if not text:
        return ""
    lines = text.split("\n")
    first = lines[0]
    match = _NUMBER_PREFIX_RE.match(first)
    if match and match.group("number") and match.end() < len(first):
        lines[0] = first[match.end() :]
    return "\n".join(lines).strip()


def _alias_form(value: str) -> str:
    cleaned = unicodedata.normalize("NFKC", value or "")
    cleaned = _SOFT_HYPHEN_RE.sub("", cleaned)
    cleaned = _SPACE_RE.sub(" ", cleaned).strip().casefold()
    return cleaned
