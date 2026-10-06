# =============================================================================
# File: result_schemas.py
# Module/Service: Extraction Service (FR7)
# Layer: Schema
# Purpose: Per-type Pydantic schemas for structured Information Extraction.
# Responsibilities:
#   - Validate payloads for table gallery, figures, entities, timeline
#   - Provide deterministic table-ready conversion helpers
# Dependencies:
#   - pydantic
# Public Exports:
#   - DocumentTableItem, TableExtractionResult, FiguresExtractionResult,
#     EntitiesExtractionResult, TimelineExtractionResult, TableRepresentation,
#     to_table_representation, *_result_to_dict
# Database/Table: extractions.result_json (shape contract)
# Related Modules: extraction_service, prompts, markdown_tables
# Important Notes:
#   - extraction_type=table is a gallery of original document tables
#     ``{tables: [...]}`` (0 LLM; Markdown parsers allowed for this type only).
#   - figures / entities / timeline still use LLM (or entity reuse) paths.
# =============================================================================

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentTableItem(BaseModel):
    """One original table recovered from a document chunk."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_chunk_id: uuid.UUID
    page_number: int | None = None
    heading_path: str | None = None
    headers: list[str] = Field(min_length=1)
    rows: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("headers")
    @classmethod
    def _unique_headers(cls, value: list[str]) -> list[str]:
        cleaned = [h.strip() for h in value if isinstance(h, str) and h.strip()]
        if not cleaned:
            raise ValueError("headers must contain at least one non-empty column")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("headers must be unique")
        return cleaned


class TableExtractionResult(BaseModel):
    """Gallery of original tables found in the document version."""

    model_config = ConfigDict(extra="forbid")

    tables: list[DocumentTableItem] = Field(default_factory=list)


class FigureItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str = Field(min_length=1)
    value: float | int | str
    unit: str | None = None
    context: str | None = None


class FiguresExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    figures: list[FigureItem] = Field(default_factory=list)


class EntityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID | None = None
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    description: str | None = None


class EntitiesExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[EntityItem] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_or_period: str = Field(min_length=1)
    event: str = Field(min_length=1)
    source_chunk_id: uuid.UUID


class TimelineExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[TimelineEvent] = Field(default_factory=list)


class TableRepresentation(BaseModel):
    """Deterministic table-ready view for non-table types with output_format=table."""

    model_config = ConfigDict(extra="forbid")

    headers: list[str]
    rows: list[dict[str, Any]]


def table_result_to_dict(result: TableExtractionResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def figures_result_to_dict(result: FiguresExtractionResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def entities_result_to_dict(result: EntitiesExtractionResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def timeline_result_to_dict(result: TimelineExtractionResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def to_table_representation(canonical: dict[str, Any], *, extraction_type: str) -> dict[str, Any]:
    """Derive headers+rows (or table gallery) from a validated canonical result."""
    if extraction_type == "table":
        return TableExtractionResult.model_validate(
            {"tables": list(canonical.get("tables") or [])}
        ).model_dump(mode="json")

    if extraction_type == "figures":
        headers = ["metric", "value", "unit", "context"]
        rows: list[dict[str, Any]] = []
        for item in canonical.get("figures") or []:
            rows.append(
                {
                    "metric": item.get("metric"),
                    "value": item.get("value"),
                    "unit": item.get("unit"),
                    "context": item.get("context"),
                }
            )
        return TableRepresentation(headers=headers, rows=rows).model_dump(mode="json")

    if extraction_type == "entities":
        headers = ["id", "name", "type", "description"]
        rows = []
        for item in canonical.get("entities") or []:
            rows.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "description": item.get("description"),
                }
            )
        return TableRepresentation(headers=headers, rows=rows).model_dump(mode="json")

    if extraction_type == "timeline":
        headers = ["date_or_period", "event", "source_chunk_id"]
        rows = []
        for item in canonical.get("events") or []:
            rows.append(
                {
                    "date_or_period": item.get("date_or_period"),
                    "event": item.get("event"),
                    "source_chunk_id": item.get("source_chunk_id"),
                }
            )
        return TableRepresentation(headers=headers, rows=rows).model_dump(mode="json")

    raise ValueError(f"unsupported extraction_type for table representation: {extraction_type}")
