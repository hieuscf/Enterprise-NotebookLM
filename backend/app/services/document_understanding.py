# =============================================================================
# File: document_understanding.py
# Module/Service: Document Ingestion Service — Document Understanding
# Layer: Service
# Purpose: Business logic for v3 Document Understanding — parse source files into
#   Markdown + Layout Analysis + Metadata Extraction (FR2, UC2, TASKS 1.4).
# Responsibilities:
#   - Validate inputs before invoking a parser
#   - Download source bytes, parse, build layout, extract metadata
#   - Persist Markdown / layout / interim segments artifacts with rollback
#   - Support idempotent skip when durable outputs already exist
# Dependencies:
#   - app.adapters.llamaparse, app.adapters.minio_storage, app.ai.layout,
#     app.ai.ocr (local parser), app.workers.artifacts, app.core.config
# Public Exports:
#   - DocumentUnderstandingService, DocumentUnderstandingResult
#   - DocumentParser, LlamaParseDocumentParser, LocalOcrDocumentParser
#   - PARSER_LLAMAPARSE, PARSER_LOCAL_OCR, SUPPORTED_FILE_TYPES
#   - build_document_understanding_service
# Database/Table: document_versions (parser, markdown_storage_path, layout_metadata)
# Related Modules: app.workers.stages.document_understanding
# Important Notes:
#   - NO LLM Provider (Anthropic) call here — parsers are external API or local OCR.
#   - Parser selection is explicit via Settings.document_parser; no silent fallback.
#   - DB updates stay in the Celery stage; this service is fully mockable for tests.
# =============================================================================

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from minio.error import S3Error

from app.adapters.llamaparse import (
    LlamaParseCircuitOpenError,
    LlamaParseClient,
    LlamaParseError,
    LlamaParseRequestError,
    LlamaParseServiceError,
    LlamaParseTimeoutError,
)
from app.adapters.minio_storage import MinioStorageAdapter
from app.ai.layout import (
    PAGINATED_FILE_TYPES,
    LayoutAnalysis,
    MarkdownMetrics,
    build_layout_analysis,
    build_layout_artifact,
    build_layout_metadata,
    build_ocr_segments,
    extract_markdown_metrics,
    resolve_page_count,
)
from app.core.config import Settings
from app.core.logging import get_logger
from app.models.documents import Document, DocumentVersion
from app.models.enums import FileType
from app.workers.artifacts import (
    LAYOUT_ARTIFACT,
    MARKDOWN_ARTIFACT,
    OCR_SEGMENTS_ARTIFACT,
    load_json_artifact,
    pipeline_artifact_key,
    save_json_artifact,
    save_text_output,
)
from app.workers.pipeline_errors import DataPipelineError, TransientPipelineError

logger = get_logger(__name__)

PARSER_LLAMAPARSE = "llamaparse"
PARSER_LOCAL_OCR = "local-ocr"
SUPPORTED_FILE_TYPES = frozenset(FileType)


@dataclass(frozen=True, slots=True)
class ParseOutput:
    """Parser-agnostic output feeding Layout Analysis."""

    markdown: str
    item_pages: list[dict[str, Any]]
    reported_page_count: int
    job_id: str | None = None
    tier: str | None = None
    attempts: int = 1
    parse_duration_ms: int = 0


@dataclass(frozen=True, slots=True)
class DocumentUnderstandingResult:
    """Service output consumed by the Celery stage for DB persistence."""

    parser: str
    markdown_storage_path: str
    layout_metadata: dict[str, Any]
    stage_metadata: dict[str, Any]
    artifact_keys: tuple[str, ...]


class DocumentParser(Protocol):
    """Pluggable document parser (LlamaParse REST API or local OCR)."""

    parser_name: str

    def parse(
        self,
        *,
        data: bytes,
        storage_path: str,
        file_type: FileType,
    ) -> ParseOutput: ...


class LlamaParseDocumentParser:
    """LlamaParse adapter implementing ``DocumentParser``."""

    parser_name = PARSER_LLAMAPARSE

    def __init__(self, client: LlamaParseClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    def parse(
        self,
        *,
        data: bytes,
        storage_path: str,
        file_type: FileType,
    ) -> ParseOutput:
        filename = storage_path.rsplit("/", 1)[-1] or f"document.{file_type.value}"
        logger.info(
            "Calling LlamaParse",
            filename=filename,
            file_type=file_type.value,
            tier=self._settings.llamaparse_tier,
            timeout_seconds=self._settings.llamaparse_timeout_seconds,
            max_retries=self._settings.llamaparse_max_retries,
        )
        try:
            result = self._client.parse(data=data, filename=filename, file_type=file_type)
        except LlamaParseCircuitOpenError as exc:
            raise DataPipelineError("LlamaParse circuit breaker open") from exc
        except LlamaParseTimeoutError as exc:
            raise DataPipelineError(
                f"LlamaParse timed out after {self._settings.llamaparse_max_retries} attempt(s) "
                f"({self._settings.llamaparse_timeout_seconds}s budget each): {exc}"
            ) from exc
        except LlamaParseServiceError as exc:
            raise DataPipelineError(
                f"LlamaParse unavailable after {self._settings.llamaparse_max_retries} "
                f"attempt(s): {exc}"
            ) from exc
        except LlamaParseRequestError as exc:
            raise DataPipelineError(f"LlamaParse rejected the document: {exc}") from exc
        except LlamaParseError as exc:
            raise DataPipelineError(f"LlamaParse failed: {exc}") from exc

        logger.info(
            "LlamaParse finished",
            job_id=result.job_id,
            attempts=result.attempts,
            parse_duration_ms=result.duration_ms,
            page_count=result.page_count,
        )
        return ParseOutput(
            markdown=result.markdown,
            item_pages=result.pages,
            reported_page_count=result.page_count,
            job_id=result.job_id,
            tier=result.tier,
            attempts=result.attempts,
            parse_duration_ms=result.duration_ms,
        )


class LocalOcrDocumentParser:
    """Offline parser for dev/CI when ``DOCUMENT_PARSER=local``."""

    parser_name = PARSER_LOCAL_OCR

    def parse(
        self,
        *,
        data: bytes,
        storage_path: str,
        file_type: FileType,
    ) -> ParseOutput:
        from app.ai.ocr import EmptyOcrError, run_ocr_cleaning

        started = time.perf_counter()
        try:
            result = run_ocr_cleaning(file_type=file_type, data=data)
        except EmptyOcrError as exc:
            raise DataPipelineError(str(exc)) from exc
        except (ValueError, OSError) as exc:
            raise DataPipelineError(f"Local parse failed for {file_type.value}: {exc}") from exc
        except Exception as exc:
            raise DataPipelineError(f"Local parse error ({file_type.value}): {exc}") from exc

        item_pages = _segments_to_item_pages(result.segments)
        return ParseOutput(
            markdown=_markdown_from_item_pages(item_pages),
            item_pages=item_pages,
            reported_page_count=result.page_count if file_type in PAGINATED_FILE_TYPES else 0,
            parse_duration_ms=int((time.perf_counter() - started) * 1000),
        )


class DocumentUnderstandingService:
    """Parse one document version into Markdown, layout artifacts and metadata."""

    def __init__(
        self,
        *,
        storage: MinioStorageAdapter,
        settings: Settings,
        parser: DocumentParser,
    ) -> None:
        self._storage = storage
        self._settings = settings
        self._parser = parser

    def execute(
        self,
        *,
        document_version_id: UUID,
        version: DocumentVersion,
        document: Document,
        force_reparse: bool = False,
    ) -> DocumentUnderstandingResult:
        """Run Document Understanding for one version (no DB writes).

        Args:
            document_version_id: Target ``document_versions.id``.
            version: Loaded ORM row (validated by caller).
            document: Parent document row (validated by caller).
            force_reparse: When False, skip parsing if durable outputs exist.

        Returns:
            Parsed outputs and stage metadata for the Celery stage to persist.

        Raises:
            DataPipelineError: Validation, parse, or empty-content failures.
            TransientPipelineError: Temporary MinIO read/write failures.
        """
        started = time.perf_counter()
        self._validate_inputs(version=version, document=document)

        if not force_reparse and self._should_skip_reparse(version):
            logger.info(
                "Skipping document understanding reparse",
                document_version_id=str(document_version_id),
                markdown_storage_path=version.markdown_storage_path,
            )
            return self._result_from_existing(
                document_version_id=document_version_id,
                version=version,
                document=document,
                started=started,
            )

        logger.info(
            "Start parsing document",
            document_version_id=str(document_version_id),
            parser=self._parser.parser_name,
            file_type=document.file_type.value,
            storage_path=version.storage_path,
        )

        raw = self._download_bytes(version.storage_path)
        logger.info(
            "Downloaded source",
            document_version_id=str(document_version_id),
            byte_length=len(raw),
        )

        output = self._parser.parse(
            data=raw,
            storage_path=version.storage_path,
            file_type=document.file_type,
        )

        metrics = extract_markdown_metrics(output.markdown)
        analysis = build_layout_analysis(
            markdown=output.markdown,
            item_pages=output.item_pages,
            reported_page_count=output.reported_page_count,
        )
        if not analysis.blocks:
            raise DataPipelineError(
                "Document Understanding produced no layout blocks — "
                "the parsed Markdown has no usable content"
            )

        parser = self._parser.parser_name
        keys = self._persist_outputs(
            document_version_id=document_version_id,
            storage_path=version.storage_path,
            file_type=document.file_type,
            parser=parser,
            markdown=output.markdown,
            analysis=analysis,
            metrics=metrics,
            job_id=output.job_id,
        )

        layout_metadata = build_layout_metadata(
            analysis=analysis,
            metrics=metrics,
            parser=parser,
            tier=output.tier,
            job_id=output.job_id,
            layout_artifact_key=keys["layout_artifact_key"],
        )
        page_count = resolve_page_count(analysis=analysis, file_type=document.file_type)

        stage_metadata = {
            "document_version_id": str(document_version_id),
            "file_type": document.file_type.value,
            "parser": parser,
            "layout_source": analysis.source,
            "llamaparse_job_id": output.job_id,
            "llamaparse_tier": output.tier,
            "llamaparse_attempts": output.attempts if parser == PARSER_LLAMAPARSE else None,
            "parse_duration_ms": output.parse_duration_ms,
            "page_count": page_count,
            "section_count": analysis.section_count,
            "block_count": len(analysis.blocks),
            "segment_count": keys["segment_count"],
            "markdown_bytes": len(output.markdown.encode("utf-8")),
            **metrics.as_dict(),
            "markdown_storage_path": keys["markdown_storage_path"],
            "layout_artifact_key": keys["layout_artifact_key"],
            "artifact_key": keys["segments_artifact_key"],
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

        artifact_keys = (
            keys["markdown_storage_path"],
            keys["layout_artifact_key"],
            keys["segments_artifact_key"],
        )

        logger.info(
            "Document understanding completed",
            document_version_id=str(document_version_id),
            parser=parser,
            segment_count=keys["segment_count"],
            duration_ms=stage_metadata["duration_ms"],
        )

        return DocumentUnderstandingResult(
            parser=parser,
            markdown_storage_path=keys["markdown_storage_path"],
            layout_metadata=layout_metadata,
            stage_metadata=stage_metadata,
            artifact_keys=artifact_keys,
        )

    def rollback_artifacts(self, artifact_keys: tuple[str, ...]) -> None:
        """Best-effort delete of uploaded objects after a downstream failure."""
        for key in reversed(artifact_keys):
            logger.warning("Rolling back artifact upload", object_key=key)
            self._storage.delete_object(key)

    def _validate_inputs(self, *, version: DocumentVersion, document: Document) -> None:
        if not version.storage_path or not version.storage_path.strip():
            raise DataPipelineError(
                f"document_version {version.id} has no storage_path — cannot parse"
            )
        if document.file_type not in SUPPORTED_FILE_TYPES:
            raise DataPipelineError(
                f"Unsupported file type for document understanding: {document.file_type.value}"
            )

    def _should_skip_reparse(self, version: DocumentVersion) -> bool:
        return bool(
            version.markdown_storage_path
            and version.markdown_storage_path.strip()
            and version.layout_metadata
        )

    def _result_from_existing(
        self,
        *,
        document_version_id: UUID,
        version: DocumentVersion,
        document: Document,
        started: float,
    ) -> DocumentUnderstandingResult:
        layout = version.layout_metadata or {}
        metrics_dict = layout.get("metrics") or {}
        parser = version.parser or layout.get("parser") or self._parser.parser_name
        layout_artifact_key = layout.get("layout_artifact_key") or pipeline_artifact_key(
            version.storage_path,
            LAYOUT_ARTIFACT,
        )
        segments_artifact_key = pipeline_artifact_key(
            version.storage_path,
            OCR_SEGMENTS_ARTIFACT,
        )
        segment_count = self._resolve_segment_count(
            storage_path=version.storage_path,
            layout=layout,
        )

        stage_metadata = {
            "document_version_id": str(document_version_id),
            "file_type": document.file_type.value,
            "parser": parser,
            "layout_source": layout.get("source"),
            "llamaparse_job_id": layout.get("job_id"),
            "llamaparse_tier": layout.get("tier"),
            "llamaparse_attempts": None,
            "parse_duration_ms": 0,
            "page_count": resolve_page_count_from_layout(layout, document.file_type),
            "section_count": layout.get("section_count", 0),
            "block_count": layout.get("block_count", len(layout.get("blocks") or [])),
            "segment_count": segment_count,
            "markdown_bytes": metrics_dict.get("char_count", 0),
            "heading_counts_by_level": metrics_dict.get("heading_counts_by_level", {}),
            "heading_count": metrics_dict.get("heading_count", 0),
            "table_count": metrics_dict.get("table_count", 0),
            "figure_count": metrics_dict.get("figure_count", 0),
            "word_count": metrics_dict.get("word_count", 0),
            "char_count": metrics_dict.get("char_count", 0),
            "markdown_storage_path": version.markdown_storage_path,
            "layout_artifact_key": layout_artifact_key,
            "artifact_key": segments_artifact_key,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }

        return DocumentUnderstandingResult(
            parser=parser,
            markdown_storage_path=version.markdown_storage_path,
            layout_metadata=layout,
            stage_metadata=stage_metadata,
            artifact_keys=(),
        )

    def _resolve_segment_count(self, *, storage_path: str, layout: dict[str, Any]) -> int:
        try:
            payload = load_json_artifact(
                self._storage,
                storage_path=storage_path,
                artifact_name=OCR_SEGMENTS_ARTIFACT,
            )
            count = payload.get("segment_count")
            if isinstance(count, int):
                return count
            segments = payload.get("segments")
            if isinstance(segments, list):
                return len(segments)
        except Exception:
            logger.warning(
                "Could not load segments artifact for idempotent metadata; "
                "falling back to layout block_count",
                storage_path=storage_path,
            )
        return int(layout.get("block_count") or len(layout.get("blocks") or []))

    def _download_bytes(self, storage_path: str) -> bytes:
        try:
            data = self._storage.download_bytes(storage_path)
        except S3Error as exc:
            code = getattr(exc, "code", "") or ""
            if code in {"NoSuchKey", "NoSuchBucket", "NotFound"}:
                raise DataPipelineError(
                    f"Source file missing in object storage: {storage_path}"
                ) from exc
            raise TransientPipelineError(f"MinIO download failed: {exc}") from exc
        except OSError as exc:
            raise TransientPipelineError(f"MinIO download I/O error: {exc}") from exc

        if not data:
            raise DataPipelineError("Source file in object storage is empty")
        return data

    def _persist_outputs(
        self,
        *,
        document_version_id: UUID,
        storage_path: str,
        file_type: FileType,
        parser: str,
        markdown: str,
        analysis: LayoutAnalysis,
        metrics: MarkdownMetrics,
        job_id: str | None,
    ) -> dict[str, Any]:
        """Write artifacts sequentially; rollback prior uploads on mid-flight failure."""
        segments = build_ocr_segments(analysis=analysis, file_type=file_type)
        if not segments:
            raise DataPipelineError(
                "Document Understanding produced no text segments — nothing to chunk"
            )

        uploaded_keys: list[str] = []
        try:
            logger.info("Persist markdown", document_version_id=str(document_version_id))
            markdown_key = save_text_output(
                self._storage,
                storage_path=storage_path,
                output_name=MARKDOWN_ARTIFACT,
                text=markdown,
            )
            uploaded_keys.append(markdown_key)

            logger.info("Persist layout", document_version_id=str(document_version_id))
            layout_key = save_json_artifact(
                self._storage,
                storage_path=storage_path,
                artifact_name=LAYOUT_ARTIFACT,
                payload=build_layout_artifact(
                    document_version_id=str(document_version_id),
                    analysis=analysis,
                    metrics=metrics,
                    parser=parser,
                    job_id=job_id,
                ),
            )
            uploaded_keys.append(layout_key)

            segments_key = save_json_artifact(
                self._storage,
                storage_path=storage_path,
                artifact_name=OCR_SEGMENTS_ARTIFACT,
                payload={
                    "document_version_id": str(document_version_id),
                    "file_type": file_type.value,
                    "parser": parser,
                    "page_count": analysis.page_count,
                    "heading_count": metrics.heading_count,
                    "table_count": metrics.table_count,
                    "segment_count": len(segments),
                    "segments": segments,
                },
            )
            uploaded_keys.append(segments_key)
        except S3Error as exc:
            self.rollback_artifacts(tuple(uploaded_keys))
            raise TransientPipelineError(f"Failed to store parse outputs: {exc}") from exc
        except OSError as exc:
            self.rollback_artifacts(tuple(uploaded_keys))
            raise TransientPipelineError(f"MinIO upload I/O error: {exc}") from exc

        return {
            "markdown_storage_path": markdown_key,
            "layout_artifact_key": layout_key,
            "segments_artifact_key": segments_key,
            "segment_count": len(segments),
        }


def build_document_understanding_service(
    *,
    storage: MinioStorageAdapter,
    settings: Settings,
    llamaparse_client: LlamaParseClient | None = None,
) -> DocumentUnderstandingService:
    """Factory wiring the configured parser into a service instance."""
    parser = resolve_document_parser(
        settings=settings,
        llamaparse_client=llamaparse_client,
    )
    return DocumentUnderstandingService(
        storage=storage,
        settings=settings,
        parser=parser,
    )


def resolve_document_parser(
    *,
    settings: Settings,
    llamaparse_client: LlamaParseClient | None = None,
) -> DocumentParser:
    """Select and validate the configured document parser."""
    if settings.document_parser == "llamaparse":
        api_key = (settings.llamaparse_api_key or "").strip()
        if not api_key:
            raise DataPipelineError(
                "Document parser configuration error: DOCUMENT_PARSER=llamaparse "
                "requires LLAMAPARSE_API_KEY"
            )
        client = llamaparse_client or LlamaParseClient(settings)
        return LlamaParseDocumentParser(client=client, settings=settings)

    if settings.document_parser == "local":
        return LocalOcrDocumentParser()

    raise DataPipelineError(
        f"Document parser configuration error: unsupported DOCUMENT_PARSER="
        f"{settings.document_parser!r} (expected 'llamaparse' or 'local')"
    )


def resolve_page_count_from_layout(layout: dict[str, Any], file_type: FileType) -> int:
    """Derive page_count from stored layout_metadata during idempotent skip."""
    page_count = layout.get("page_count") or 0
    section_count = layout.get("section_count") or 0
    if file_type in PAGINATED_FILE_TYPES:
        return max(1, int(page_count))
    return max(1, int(section_count))


def _segments_to_item_pages(segments: list[Any]) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    current_page: int | None = -1

    for segment in segments:
        text = (getattr(segment, "text", "") or "").strip()
        if not text:
            continue
        page_number = getattr(segment, "page_number", None)
        if not pages or page_number != current_page:
            pages.append({"page_number": page_number, "items": []})
            current_page = page_number

        item: dict[str, Any] = {
            "type": getattr(segment, "block_type", None) or "paragraph",
            "md": text,
        }
        level = getattr(segment, "heading_level", None)
        if level:
            item["lvl"] = level
        bbox = getattr(segment, "bbox", None)
        if bbox:
            item["bbox"] = list(bbox)
        pages[-1]["items"].append(item)

    return pages


def _markdown_from_item_pages(item_pages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for page in item_pages:
        for item in page["items"]:
            text = item["md"]
            if item["type"] == "heading":
                level = min(6, max(1, int(item.get("lvl") or 1)))
                parts.append(f"{'#' * level} {text}")
            else:
                parts.append(text)
    return "\n\n".join(parts)
