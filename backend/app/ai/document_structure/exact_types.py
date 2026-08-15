# =============================================================================
# File: exact_types.py
# Module/Service: Exact Difference Detection (FR8 / TASK-CMP-06)
# Layer: Service
# Purpose: Domain types for deterministic typed value changes after CMP-04.
# Responsibilities:
#   - Value/change/direction enums, extracted values, ExactChange rows
#   - Evidence refs reuse ClauseRef; originals are never rewritten
# Dependencies:
#   - mapping_types.ClauseRef; stdlib Decimal / date
# Public Exports:
#   - ValueType, ValueChangeType, ValueDirection, ParseStatus, Qualifier,
#     DurationKind, ExtractedValue, ExactChange, ExactDiffResult
# Database/Table: N/A (runtime domain; not persisted)
# Related Modules: exact_engine; CMP-07 consumes ExactChange facts only
# Important Notes:
#   - Not a legal-risk label. No LLM. as_dict() omits full clause text.
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.ai.document_structure.mapping_types import ClauseRef


class ValueType(StrEnum):
    MONEY = "MONEY"
    PERCENTAGE = "PERCENTAGE"
    DATE = "DATE"
    DURATION = "DURATION"
    QUANTITY = "QUANTITY"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    NUMBER = "NUMBER"


class ValueChangeType(StrEnum):
    UNCHANGED_VALUE = "UNCHANGED_VALUE"
    ADDED_VALUE = "ADDED_VALUE"
    REMOVED_VALUE = "REMOVED_VALUE"
    REPLACED_VALUE = "REPLACED_VALUE"
    FORMAT_ONLY = "FORMAT_ONLY"


class ValueDirection(StrEnum):
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    UNCHANGED = "UNCHANGED"
    REPLACED = "REPLACED"
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    LATER = "LATER"
    EARLIER = "EARLIER"
    UNKNOWN = "UNKNOWN"


class ParseStatus(StrEnum):
    PARSED = "PARSED"
    UNPARSED = "UNPARSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNAVAILABLE = "UNAVAILABLE"


class Qualifier(StrEnum):
    EQUAL = "EQUAL"
    AT_LEAST = "AT_LEAST"
    AT_MOST = "AT_MOST"
    GREATER = "GREATER"
    LESS = "LESS"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


class DurationKind(StrEnum):
    CALENDAR_DAY = "CALENDAR_DAY"
    BUSINESS_DAY = "BUSINESS_DAY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ExtractedValue:
    """One typed value found in a clause. Offsets are into the scanned text."""

    value_type: ValueType
    raw_text: str
    start: int
    end: int
    number: Decimal | None = None
    number_max: Decimal | None = None
    currency: str | None = None
    unit: str | None = None
    duration_kind: DurationKind | None = None
    iso_date: date | None = None
    entity_text: str | None = None
    qualifier: Qualifier = Qualifier.EQUAL
    parse_status: ParseStatus = ParseStatus.PARSED
    sentence: str = ""
    left_context: str = ""
    right_context: str = ""
    index_in_type: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "value_type": self.value_type.value,
            "raw": self.raw_text,
            "value": _dec_str(self.number),
            "value_max": _dec_str(self.number_max),
            "currency": self.currency,
            "unit": self.unit,
            "duration_kind": self.duration_kind.value if self.duration_kind else None,
            "iso_date": self.iso_date.isoformat() if self.iso_date else None,
            "entity_text": self.entity_text,
            "qualifier": self.qualifier.value,
            "parse_status": self.parse_status.value,
            "start": self.start,
            "end": self.end,
        }


@dataclass
class ExactChange:
    """One aligned old/new value. Facts only — no risk interpretation."""

    change_type: ValueChangeType
    value_type: ValueType
    direction: ValueDirection
    old_value: ExtractedValue | None
    new_value: ExtractedValue | None
    source_ref: ClauseRef | None
    target_ref: ClauseRef | None
    delta: Decimal | None = None
    relative_change_percent: Decimal | None = None
    delta_unit: str | None = None
    currency_changed: bool = False
    parse_status: ParseStatus = ParseStatus.PARSED
    source_span_status: ParseStatus = ParseStatus.UNAVAILABLE
    target_span_status: ParseStatus = ParseStatus.UNAVAILABLE
    source_offset: tuple[int, int] | None = None
    target_offset: tuple[int, int] | None = None
    context: str = ""
    alignment_method: str = "unaligned"

    def as_dict(self) -> dict[str, Any]:
        return {
            "change_type": self.change_type.value,
            "value_type": self.value_type.value,
            "direction": self.direction.value,
            "old": self.old_value.as_dict() if self.old_value else None,
            "new": self.new_value.as_dict() if self.new_value else None,
            "delta": _dec_str(self.delta),
            "relative_change_percent": _dec_str(self.relative_change_percent),
            "delta_unit": self.delta_unit,
            "currency_changed": self.currency_changed,
            "parse_status": self.parse_status.value,
            "source_span_status": self.source_span_status.value,
            "target_span_status": self.target_span_status.value,
            "source_offset": (
                list(self.source_offset) if self.source_offset else None
            ),
            "target_offset": (
                list(self.target_offset) if self.target_offset else None
            ),
            "context": self.context,
            "alignment_method": self.alignment_method,
            "source_ref": self.source_ref.as_dict() if self.source_ref else None,
            "target_ref": self.target_ref.as_dict() if self.target_ref else None,
        }


@dataclass
class ExactDiffResult:
    """Typed value changes for a full DiffResult. Independent of RAG / LLM."""

    source_document_id: UUID
    target_document_id: UUID
    source_version_id: UUID | None
    target_version_id: UUID | None
    changes: list[ExactChange] = field(default_factory=list)
    diff_metadata: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def for_source(self, identity_key: str) -> list[ExactChange]:
        return [
            row
            for row in self.changes
            if row.source_ref and row.source_ref.identity_key == identity_key
        ]

    def for_target(self, identity_key: str) -> list[ExactChange]:
        return [
            row
            for row in self.changes
            if row.target_ref and row.target_ref.identity_key == identity_key
        ]

    def by_value_type(self, value_type: ValueType) -> list[ExactChange]:
        return [row for row in self.changes if row.value_type is value_type]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_document_id": str(self.source_document_id),
            "target_document_id": str(self.target_document_id),
            "source_version_id": (
                str(self.source_version_id) if self.source_version_id else None
            ),
            "target_version_id": (
                str(self.target_version_id) if self.target_version_id else None
            ),
            "changes": [row.as_dict() for row in self.changes],
            "diff_metadata": dict(self.diff_metadata),
            "metadata": dict(self.metadata),
        }


def _dec_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
