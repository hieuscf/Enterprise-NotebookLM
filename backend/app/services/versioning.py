# =============================================================================
# File: versioning.py
# Module/Service: Document Ingestion Service
# Layer: Service
# Purpose: Workspace version catalog, edit history, and classification labels.
# Responsibilities:
#   - List versions and append-only edit events scoped by workspace_id
#   - Validate tags and classification metadata
#   - Persist label changes as document_version_events
# Dependencies:
#   - app.repositories.documents, app.services.documents.DocumentIngestionError
# Public Exports:
#   - VersioningService, normalize_tags, normalize_metadata
#   - VersionCatalogPage, VersionHistoryPage, UNSET
# Database/Table: document_versions, document_version_events, documents, users
# Related Modules: app.api.documents, app.services.documents
# Important Notes: Rollback itself lives on DocumentIngestionService so
#   set-current and rollback share one code path. This module only classifies.
# =============================================================================

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.documents import Document, DocumentVersion, DocumentVersionEvent
from app.repositories.documents import DocumentRepository
from app.services.documents import DocumentIngestionError

_TAG_RE = re.compile(r"^[\w][\w .\-]{0,39}$", re.UNICODE)
_META_KEY_RE = re.compile(r"^[\w .\-]{1,64}$", re.UNICODE)
_MAX_TAGS = 20
_MAX_METADATA_FIELDS = 20
_MAX_METADATA_VALUE = 500
_MAX_NOTE = 2000

EVENT_TAGS_UPDATED = "tags_updated"
EVENT_METADATA_UPDATED = "metadata_updated"


class _UnsetType:
    """Marker: the caller omitted change_note, so leave the stored note alone."""


UNSET = _UnsetType()


@dataclass(frozen=True, slots=True)
class VersionCatalogEntry:
    version: DocumentVersion
    document: Document
    uploader_name: str | None
    uploader_email: str | None


@dataclass(frozen=True, slots=True)
class VersionCatalogPage:
    items: list[VersionCatalogEntry]
    page: int
    page_size: int
    total: int
    available_tags: list[str]


@dataclass(frozen=True, slots=True)
class VersionHistoryEntry:
    event: DocumentVersionEvent
    document_title: str
    version_number: int
    actor_name: str | None


@dataclass(frozen=True, slots=True)
class VersionHistoryPage:
    items: list[VersionHistoryEntry]
    page: int
    page_size: int
    total: int


def normalize_tags(tags: list[str]) -> list[str]:
    """Trim, case-fold, and de-duplicate classification tags."""
    if len(tags) > _MAX_TAGS:
        raise DocumentIngestionError(
            "too_many_tags",
            f"A version can have at most {_MAX_TAGS} tags",
            status_code=400,
        )
    seen: list[str] = []
    for raw in tags:
        if not isinstance(raw, str):
            raise DocumentIngestionError(
                "invalid_tag",
                "Each tag must be a string",
                status_code=400,
            )
        tag = " ".join(raw.strip().split()).casefold()
        if not tag:
            continue
        if not _TAG_RE.match(tag):
            raise DocumentIngestionError(
                "invalid_tag",
                (
                    f"Tag '{raw.strip()[:40]}' is invalid. Use letters, numbers, "
                    "spaces, dots, underscores, or hyphens (max 40 characters)."
                ),
                status_code=400,
            )
        if tag not in seen:
            seen.append(tag)
    return seen


def normalize_metadata(metadata: dict[str, str]) -> dict[str, str]:
    """Validate classification key/value pairs. Keys are trimmed, not case-folded."""
    if len(metadata) > _MAX_METADATA_FIELDS:
        raise DocumentIngestionError(
            "too_many_metadata_fields",
            f"A version can have at most {_MAX_METADATA_FIELDS} metadata fields",
            status_code=400,
        )
    cleaned: dict[str, str] = {}
    for raw_key, raw_value in metadata.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            raise DocumentIngestionError(
                "invalid_metadata",
                "Metadata keys and values must be strings",
                status_code=400,
            )
        key = " ".join(raw_key.strip().split())
        value = raw_value.strip()
        if not key:
            raise DocumentIngestionError(
                "invalid_metadata",
                "Metadata keys cannot be empty",
                status_code=400,
            )
        if not _META_KEY_RE.match(key):
            raise DocumentIngestionError(
                "invalid_metadata",
                (
                    f"Metadata key '{key[:64]}' is invalid. Use letters, numbers, "
                    "spaces, dots, underscores, or hyphens (max 64 characters)."
                ),
                status_code=400,
            )
        if len(value) > _MAX_METADATA_VALUE:
            raise DocumentIngestionError(
                "invalid_metadata",
                f"Metadata value for '{key}' exceeds {_MAX_METADATA_VALUE} characters",
                status_code=400,
            )
        cleaned[key] = value
    return cleaned


def _clean_note(note: str | None) -> str | None:
    if note is None:
        return None
    text = note.strip()
    if len(text) > _MAX_NOTE:
        raise DocumentIngestionError(
            "invalid_note",
            f"Change note exceeds {_MAX_NOTE} characters",
            status_code=400,
        )
    return text or None


def _page_bounds(page: int, page_size: int) -> tuple[int, int]:
    if page < 1:
        raise DocumentIngestionError("invalid_page", "page must be >= 1", status_code=400)
    if page_size < 1 or page_size > 100:
        raise DocumentIngestionError(
            "invalid_page_size",
            "page_size must be between 1 and 100",
            status_code=400,
        )
    return page, page_size


class VersioningService:
    def __init__(self, session: AsyncSession) -> None:
        self._docs = DocumentRepository(session)

    async def list_catalog(
        self,
        workspace_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        document_id: uuid.UUID | None = None,
        tag: str | None = None,
        query: str | None = None,
    ) -> VersionCatalogPage:
        page, page_size = _page_bounds(page, page_size)
        cleaned_tag = tag.strip().casefold() if tag and tag.strip() else None
        cleaned_query = query.strip() if query and query.strip() else None
        if cleaned_tag and not _TAG_RE.match(cleaned_tag):
            raise DocumentIngestionError(
                "invalid_tag",
                "Tag filter is invalid",
                status_code=400,
            )
        rows, total = await self._docs.list_workspace_versions(
            workspace_id,
            page=page,
            page_size=page_size,
            document_id=document_id,
            tag=cleaned_tag,
            query=cleaned_query,
        )
        tags = await self._docs.list_workspace_tags(workspace_id)
        return VersionCatalogPage(
            items=[
                VersionCatalogEntry(
                    version=version,
                    document=document,
                    uploader_name=uploader_name,
                    uploader_email=uploader_email,
                )
                for version, document, uploader_name, uploader_email in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
            available_tags=tags,
        )

    async def list_history(
        self,
        workspace_id: uuid.UUID,
        *,
        page: int,
        page_size: int,
        document_id: uuid.UUID | None = None,
        query: str | None = None,
    ) -> VersionHistoryPage:
        page, page_size = _page_bounds(page, page_size)
        cleaned_query = query.strip() if query and query.strip() else None
        rows, total = await self._docs.list_version_events(
            workspace_id,
            page=page,
            page_size=page_size,
            document_id=document_id,
            query=cleaned_query,
        )
        return VersionHistoryPage(
            items=[
                VersionHistoryEntry(
                    event=event,
                    document_title=title,
                    version_number=version_number,
                    actor_name=actor_name,
                )
                for event, title, version_number, actor_name in rows
            ],
            page=page,
            page_size=page_size,
            total=total,
        )

    async def update_classification(
        self,
        *,
        workspace_id: uuid.UUID,
        document_id: uuid.UUID,
        version_id: uuid.UUID,
        actor_id: uuid.UUID,
        tags: list[str] | None,
        classification_metadata: dict[str, str] | None,
        change_note: str | None | _UnsetType,
    ) -> DocumentVersion:
        version = await self._docs.get_version(workspace_id, document_id, version_id)
        if version is None:
            raise DocumentIngestionError(
                "not_found",
                "Document version not found",
                status_code=404,
            )

        label_tags: list[str] | None = None
        label_metadata: dict[str, str] | None = None
        label_note: str | None = None
        update_note = False

        if tags is not None:
            normalized_tags = normalize_tags(tags)
            current_tags = [item for item in (version.tags or []) if isinstance(item, str)]
            if normalized_tags != current_tags:
                await self._docs.add_version_event(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version.id,
                    actor_id=actor_id,
                    event_type=EVENT_TAGS_UPDATED,
                    summary=f"Cập nhật thẻ phân loại của phiên bản v{version.version_number}",
                    payload={"before": current_tags, "after": normalized_tags},
                )
                label_tags = normalized_tags

        if classification_metadata is not None:
            normalized_meta = normalize_metadata(classification_metadata)
            current_meta = _string_map(version.classification_metadata)
            if normalized_meta != current_meta:
                await self._docs.add_version_event(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version.id,
                    actor_id=actor_id,
                    event_type=EVENT_METADATA_UPDATED,
                    summary=(
                        f"Cập nhật metadata phân loại của phiên bản v{version.version_number}"
                    ),
                    payload={
                        "field": "classification_metadata",
                        "before": current_meta,
                        "after": normalized_meta,
                    },
                )
                label_metadata = normalized_meta

        if not isinstance(change_note, _UnsetType):
            note = _clean_note(change_note if isinstance(change_note, str) else None)
            if note != version.change_note:
                await self._docs.add_version_event(
                    workspace_id=workspace_id,
                    document_id=document_id,
                    document_version_id=version.id,
                    actor_id=actor_id,
                    event_type=EVENT_METADATA_UPDATED,
                    summary=f"Cập nhật ghi chú của phiên bản v{version.version_number}",
                    payload={
                        "field": "change_note",
                        "before": version.change_note,
                        "after": note,
                    },
                )
                label_note = note
                update_note = True

        if label_tags is None and label_metadata is None and not update_note:
            return version

        return await self._docs.apply_version_labels(
            version,
            tags=label_tags,
            classification_metadata=label_metadata,
            change_note=label_note,
            update_note=update_note,
        )


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }
